#!/usr/bin/env python3
"""
CLI for Raw E-Series API Data Collection

Simple command-line interface for collecting raw API responses.
"""

import argparse
import sys
import logging
import time
from pathlib import Path

# Add the parent directory to the path so we can import from app
sys.path.insert(0, str(Path(__file__).parent))

from app.raw_collector import RawApiCollector
from app.config.endpoint_categories import EndpointCategory

def main():
    parser = argparse.ArgumentParser(
        description='Collect raw API data from E-Series systems',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Collect all endpoints from multiple hosts (single iteration)
  python3 raw_collector_cli.py --hosts 10.113.1.158 10.113.1.159 --user admin --password admin123 --output ./api_json

  # Collect only performance data with 5 iterations, 30 second intervals
  python3 raw_collector_cli.py --hosts 10.113.1.158 --user admin --password admin123 --output ./api_json --category PERFORMANCE --iterations 5 --interval 30

  # Collect configuration data from multiple hosts, 10 iterations with 60s intervals
  python3 raw_collector_cli.py --hosts 10.113.1.158 10.113.1.159 10.113.1.160 --user admin --password admin123 --output ./api_json --category CONFIGURATION --iterations 10 --interval 60
  
  # Continuous collection (1000 iterations, 5 minute intervals)
  python3 raw_collector_cli.py --hosts 10.113.1.158 --user admin --password admin123 --output ./api_json --iterations 1000 --interval 300
        """
    )

    parser.add_argument('--hosts', required=True, nargs='+',
                       help='E-Series management IP addresses (space-separated for multiple)')
    parser.add_argument('--user', default='admin',
                       help='Username (default: admin)')
    parser.add_argument('--password', required=True,
                       help='Password')
    parser.add_argument('--output', '-o', default='./api_json',
                       help='Output directory for JSON files (default: ./api_json)')
    parser.add_argument('--system-id', 
                       help='Specific system ID/WWN (optional, will auto-detect if not provided)')
    parser.add_argument('--category', choices=[cat.value for cat in EndpointCategory],
                       help='Collect only endpoints from specific category')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--iterations', type=int, default=1,
                       help='Number of collection iterations (default: 1)')
    parser.add_argument('--interval', type=int, default=60,
                       help='Interval in seconds between iterations (default: 60)')
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print(f"🎯 Collection Plan:")
    print(f"  📍 Hosts: {', '.join(args.hosts)}")
    print(f"  🔄 Iterations: {args.iterations}")
    print(f"  ⏱️  interval between iterations: {args.interval}s")
    if args.category:
        print(f"  📂 Category: {args.category}")
    else:
        print(f"  📂 Category: ALL")
    print(f"  📁 Output directory: {args.output}")
    print()
    
    # Track overall statistics
    overall_stats = {
        'total_iterations': 0,
        'successful_hosts': 0,
        'failed_hosts': 0,
        'total_endpoints_collected': 0
    }
    
    try:
        # Main collection loop - iterate over iterations and hosts
        time_begin = time.time()
        for iteration in range(1, args.iterations + 1):
            print(f"🔄 === ITERATION {iteration}/{args.iterations} ===")
            
            iteration_stats = {
                'successful_hosts': 0,
                'failed_hosts': 0,
                'total_endpoints': 0
            }
            
            # Loop through all hosts for this iteration
            for host_idx, host in enumerate(args.hosts, 1):
                print(f"\n📡 [{iteration}.{host_idx}] Processing host: {host}")
                
                # Build base URL for current host
                if '://' not in host:
                    base_url = f"https://{host}:8443"
                else:
                    base_url = host
                
                # Create collector for current host
                collector = RawApiCollector(
                    base_url=base_url,
                    username=args.user,
                    password=args.password,
                    output_dir=args.output,
                    system_id=args.system_id
                )
                
                try:
                    # Connect to current host
                    print(f"  🔌 Connecting to {base_url}...")
                    if not collector.connect():
                        print(f"  ❌ Connection failed to {host}")
                        iteration_stats['failed_hosts'] += 1
                        continue
                    
                    host_success = True
                    host_endpoints = 0
                    
                    # Collect data from current host
                    if args.category:
                        # Single category
                        category = EndpointCategory(args.category)
                        print(f"  🔄 Collecting {category.value} endpoints...")
                        results = collector.collect_by_category(category)
                        
                        success_count = sum(1 for success in results.values() if success)
                        total_count = len(results)
                        host_endpoints = success_count
                        
                        print(f"  📊 Results: {success_count}/{total_count} endpoints successful")
                        
                        if args.verbose:
                            for endpoint, success in results.items():
                                status = "✅" if success else "❌"
                                print(f"    {status} {endpoint}")
                                
                    else:
                        # All categories
                        print(f"  🔄 Collecting all endpoints...")
                        all_results = collector.collect_all()
                        
                        host_success_count = 0
                        host_total_count = 0
                        
                        if args.verbose:
                            print(f"  📊 Category Summary:")
                        for category, results in all_results.items():
                            success_count = sum(1 for success in results.values() if success)
                            category_count = len(results)
                            host_success_count += success_count
                            host_total_count += category_count
                            
                            if args.verbose:
                                print(f"    {category}: {success_count}/{category_count}")
                                
                        host_endpoints = host_success_count
                        print(f"  🎯 Host Total: {host_success_count}/{host_total_count} endpoints successful")
                    
                    if host_success:
                        iteration_stats['successful_hosts'] += 1
                        iteration_stats['total_endpoints'] += host_endpoints
                        print(f"  ✅ Host {host} completed successfully")
                    
                except KeyboardInterrupt:
                    print(f"\n⚠️  Collection interrupted by user during host {host}")
                    raise
                except Exception as e:
                    print(f"  ❌ Error collecting from host {host}: {e}")
                    iteration_stats['failed_hosts'] += 1
                    host_success = False
                finally:
                    collector.disconnect()
            
            # Iteration summary
            print(f"\n📈 Iteration {iteration} Summary:")
            print(f"  ✅ Successful hosts: {iteration_stats['successful_hosts']}")
            print(f"  ❌ Failed hosts: {iteration_stats['failed_hosts']}")
            print(f"  📊 Total endpoints collected: {iteration_stats['total_endpoints']}")
            
            # Update overall stats
            overall_stats['total_iterations'] += 1
            overall_stats['successful_hosts'] += iteration_stats['successful_hosts']
            overall_stats['failed_hosts'] += iteration_stats['failed_hosts']
            overall_stats['total_endpoints_collected'] += iteration_stats['total_endpoints']
            time_end = time.time()
            time_taken = time_end - time_begin
                        
            # Sleep between iterations (except for the last one)
            if iteration < args.iterations:
                print(f"\n⏱️  Waiting {args.interval - time_taken} seconds before next iteration...")
                time.sleep(args.interval-time_taken)
        
        # Final summary
        print(f"\n🎉 === COLLECTION COMPLETE ===")
        print(f"📊 Overall Statistics:")
        print(f"  🔄 Total iterations: {overall_stats['total_iterations']}")
        print(f"  ✅ Successful host collections: {overall_stats['successful_hosts']}")
        print(f"  ❌ Failed host collections: {overall_stats['failed_hosts']}")
        print(f"  📊 Total endpoints collected: {overall_stats['total_endpoints_collected']}")
        print(f"  📁 Files written to: {args.output}")
        
    except KeyboardInterrupt:
        print(f"\n⚠️  Collection interrupted by user")
        print(f"📊 Partial Statistics (before interruption):")
        print(f"  🔄 Completed iterations: {overall_stats['total_iterations']}")
        print(f"  ✅ Successful host collections: {overall_stats['successful_hosts']}")
        print(f"  ❌ Failed host collections: {overall_stats['failed_hosts']}")
        print(f"  📊 Endpoints collected so far: {overall_stats['total_endpoints_collected']}")
        return 130
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())