#!/usr/bin/env bash

OUT_FILE="DATABASE.md"
INFLUX_CMD="influx -host localhost -port 8086 -database eseries"

echo "# InfluxDB Schema for E-Series Perf Analyzer" > "$OUT_FILE"
echo "" >> "$OUT_FILE"

echo "Extracting measurements..."
# Use CSV format for easy parsing of measurements, skipping the name,measurement header
$INFLUX_CMD -format csv -execute "SHOW MEASUREMENTS" > /tmp/measurements.csv
measurements=$(tail -n +2 /tmp/measurements.csv | cut -d, -f2 | grep -v "^$" | sort | uniq)

echo "## Measurements" >> "$OUT_FILE"
echo "" >> "$OUT_FILE"
for measurement in $measurements; do
    echo "- \`$measurement\`" >> "$OUT_FILE"
done
echo "" >> "$OUT_FILE"

for measurement in $measurements; do
    echo "Querying tags and fields for measurement: $measurement..."
    echo "## Measurement: \`$measurement\`" >> "$OUT_FILE"
    echo "" >> "$OUT_FILE"

    echo "### Tags" >> "$OUT_FILE"
    echo '```text' >> "$OUT_FILE"
    TAG_QUERY="SHOW TAG KEYS FROM \"$measurement\""
    $INFLUX_CMD -format column -execute "$TAG_QUERY" | sed '/^$/d' >> "$OUT_FILE"
    echo '```' >> "$OUT_FILE"
    echo "" >> "$OUT_FILE"

    echo "### Fields" >> "$OUT_FILE"
    echo '```text' >> "$OUT_FILE"
    FIELD_QUERY="SHOW FIELD KEYS FROM \"$measurement\""
    $INFLUX_CMD -format column -execute "$FIELD_QUERY" | sed '/^$/d' >> "$OUT_FILE"
    echo '```' >> "$OUT_FILE"
    echo "" >> "$OUT_FILE"
done

echo ""
echo "Schema dump complete. See $OUT_FILE for details."
