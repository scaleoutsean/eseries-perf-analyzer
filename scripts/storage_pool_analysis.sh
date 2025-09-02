#!/bin/bash
# E-Series Storage Pool Capacity Analysis
# Correlates storage pool data with volume allocation

INFLUX_HOST="${INFLUX_HOST:-influxdb}"
INFLUX_PORT="${INFLUX_PORT:-8086}"
DATABASE="eseries"
SYS_NAME="${1:-netapp_03}"

echo "=== E-Series Storage Pool Analysis for $SYS_NAME ==="
echo

# Get storage pool information
echo "Getting storage pool data..."
POOLS_QUERY="SELECT last(pool_name_field) AS \"Pool_Name\", last(totalRaidedSpace) AS \"Total_Space\", last(usedSpace) AS \"Used_Space\", last(freeSpace) AS \"Free_Space\", last(diskPool) AS \"Is_DiskPool\" FROM config_storage_pools WHERE sys_name = '$SYS_NAME' GROUP BY volumeGroupRef"

# Get volume allocation by pool
echo "Getting volume allocation data..."
VOLUMES_QUERY="SELECT SUM(last_totalSizeInBytes) AS \"Allocated_Space\" FROM (SELECT last(totalSizeInBytes) AS \"last_totalSizeInBytes\" FROM config_volumes WHERE sys_name = '$SYS_NAME' GROUP BY volumeRef) GROUP BY volumeGroupRef"

# Create temporary files
POOLS_FILE=$(mktemp)
VOLUMES_FILE=$(mktemp)

# Execute queries and save results
docker exec influxdb influx -host "$INFLUX_HOST" -port "$INFLUX_PORT" -database "$DATABASE" -format=csv -execute "$POOLS_QUERY" > "$POOLS_FILE"
docker exec influxdb influx -host "$INFLUX_HOST" -port "$INFLUX_PORT" -database "$DATABASE" -format=csv -execute "$VOLUMES_QUERY" > "$VOLUMES_FILE"

# Process and combine results
printf "%-20s %-12s %-15s %-15s %-15s %-15s %-10s\n" "Pool_Name" "Pool_Type" "Total_Space_TB" "Used_Space_TB" "Free_Space_TB" "Alloc_Space_TB" "Util_%"
printf "%-20s %-12s %-15s %-15s %-15s %-15s %-10s\n" "$(printf '%0.s-' {1..20})" "$(printf '%0.s-' {1..12})" "$(printf '%0.s-' {1..15})" "$(printf '%0.s-' {1..15})" "$(printf '%0.s-' {1..15})" "$(printf '%0.s-' {1..15})" "$(printf '%0.s-' {1..10})"

# Skip CSV header and process pool data
tail -n +2 "$POOLS_FILE" | while IFS=',' read -r name tags time pool_name total_space used_space free_space is_diskpool; do
    # Extract volumeGroupRef from tags
    vol_group_ref=$(echo "$tags" | sed 's/.*volumeGroupRef=\([^,]*\).*/\1/')
    
    # Skip empty or header-like lines
    if [[ "$pool_name" == "Pool_Name" || "$pool_name" == "" || "$name" == "name" ]]; then
        continue
    fi
    
    # Find corresponding volume allocation
    alloc_space=$(grep "$vol_group_ref" "$VOLUMES_FILE" | tail -1 | cut -d',' -f4 | tr -d '"')
    
    # Handle empty allocation (no volumes in pool)
    if [[ -z "$alloc_space" || "$alloc_space" == "" ]]; then
        alloc_space="0"
    fi
    
    # Clean up field values (remove quotes and whitespace)
    pool_name=$(echo "$pool_name" | tr -d '"' | tr -d ' ')
    total_space=$(echo "$total_space" | tr -d '"' | tr -d ' ')
    used_space=$(echo "$used_space" | tr -d '"' | tr -d ' ')
    free_space=$(echo "$free_space" | tr -d '"' | tr -d ' ')
    is_diskpool=$(echo "$is_diskpool" | tr -d '"' | tr -d ' ')
    
    # Debug output (uncomment for troubleshooting)
    # echo "DEBUG: pool_name='$pool_name' total_space='$total_space' used_space='$used_space'" >&2
    
    # Convert to TB and calculate utilization
    if [[ "$total_space" != "" && "$total_space" != "0" && "$total_space" -gt 0 ]]; then
        total_tb=$(awk "BEGIN {printf \"%.2f\", $total_space / 1099511627776}")
        used_tb=$(awk "BEGIN {printf \"%.2f\", $used_space / 1099511627776}")
        free_tb=$(awk "BEGIN {printf \"%.2f\", $free_space / 1099511627776}")
        alloc_tb=$(awk "BEGIN {printf \"%.2f\", $alloc_space / 1099511627776}")
        util_pct=$(awk "BEGIN {printf \"%.1f\", $used_space * 100 / $total_space}")
        
        # Determine pool type
        if [[ "$is_diskpool" == "true" ]]; then
            pool_type="DiskPool"
        else
            pool_type="VolumeGroup"
        fi
        
        printf "%-20s %-12s %-15s %-15s %-15s %-15s %-10s\n" \
            "$pool_name" "$pool_type" "${total_tb}TB" "${used_tb}TB" "${free_tb}TB" "${alloc_tb}TB" "${util_pct}%"
    else
        # Skip pools with zero or invalid capacity
        if [[ "$pool_name" != "" ]]; then
            echo "Skipping pool '$pool_name' - invalid or zero capacity ($total_space)" >&2
        fi
    fi
done

# Cleanup
rm -f "$POOLS_FILE" "$VOLUMES_FILE"

echo
echo "Legend:"
echo "  Total_Space_TB: Raw storage pool capacity"
echo "  Used_Space_TB:  Currently allocated storage (from storage pool perspective)"
echo "  Free_Space_TB:  Available space for new volumes"
echo "  Alloc_Space_TB: Sum of all volume sizes in this pool"
echo "  Util_%:         Percentage of pool capacity used"
echo
echo "Note: Alloc_Space_TB should roughly match Used_Space_TB (differences may exist due to snapshot reservation or other factors)"
