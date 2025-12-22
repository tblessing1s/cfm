"""
Example Usage Script for Schwab Trades Module

This script demonstrates how to use the schwab_trades module to:
1. Pull trade data from the past 7 days
2. Filter for short call sells
3. Display results and export to CSV

Prerequisites:
- schwab-py OAuth flow completed (tokens.json exists)
- Environment variables set for Schwab API credentials
- Required Python packages installed
"""

import os
import sys
from datetime import datetime, timedelta
from schwab_trades import SchwabTradesExtractor


def check_prerequisites():
    """Check if all prerequisites are met."""
    print("🔍 Checking prerequisites...")
    
    # Check if tokens.json exists
    if not os.path.exists("tokens.json"):
        print("❌ tokens.json not found!")
        print("Please run the schwab-py OAuth flow first:")
        print("1. Set environment variables: SCHWAB_API_KEY, SCHWAB_APP_SECRET")
        print("2. Run: python -c \"from schwab import auth; auth.easy_client()\"")
        return False
    
    # Check environment variables
    required_env_vars = ['SCHWAB_API_KEY', 'SCHWAB_APP_SECRET']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("Please set these environment variables before running the script.")
        return False
    
    print("✅ All prerequisites met!")
    return True


def main():
    """Main example usage function."""
    print("=" * 60)
    print("    Schwab Trades - Example Usage")
    print("=" * 60)
    
    # Check prerequisites
    if not check_prerequisites():
        print("\n❌ Prerequisites not met. Please fix the issues above.")
        return
    
    try:
        # Initialize the Schwab trades extractor
        print("\n🔧 Initializing Schwab API client...")
        extractor = SchwabTradesExtractor()
        
        # Set date range (past 7 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        print(f"\n📅 Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        # Get all trades first
        print("\n📡 Fetching all trades...")
        all_trades = extractor.get_trades_dataframe(start_date, end_date)
        
        if all_trades.empty:
            print("📭 No trades found in the specified date range")
            return
        
        print(f"✅ Found {len(all_trades)} total fills")
        
        # Show sample of all trades
        print(f"\n📊 Sample of all trades:")
        print(all_trades[['trade_time_local', 'underlying', 'right', 'strike', 'qty', 'fill_price']].head())
        
        # Filter for short calls
        print(f"\n🔍 Filtering for short call sells...")
        short_calls = extractor.filter_short_calls(all_trades)
        
        if short_calls.empty:
            print("📭 No short call sells found in the specified date range")
            print("\n💡 This could mean:")
            print("   - No short calls were made in this period")
            print("   - All short calls were buy-to-close (not sells)")
            print("   - Orders haven't been filled yet")
            return
        
        # Display short calls summary
        print(f"\n📊 Short Calls Summary:")
        print(f"Total short call sells: {len(short_calls)}")
        
        # Show detailed results
        print(f"\n📋 Short Calls Details:")
        display_columns = [
            'trade_time_local', 'underlying', 'right', 'strike', 'expiration',
            'qty', 'fill_price', 'premium', 'commission', 'net_premium'
        ]
        print(short_calls[display_columns].to_string(index=False))
        
        # Financial summary
        if len(short_calls) > 0:
            total_premium = short_calls['premium'].sum()
            total_commission = short_calls['commission'].sum()
            total_fees = short_calls['fees'].sum()
            net_premium = short_calls['net_premium'].sum()
            avg_premium_per_contract = short_calls['premium'].mean()
            
            print(f"\n💰 Financial Summary:")
            print(f"  Total Premium Received: ${total_premium:.2f}")
            print(f"  Total Commission Paid: ${total_commission:.2f}")
            print(f"  Total Fees Paid: ${total_fees:.2f}")
            print(f"  Net Premium: ${net_premium:.2f}")
            print(f"  Average Premium per Contract: ${avg_premium_per_contract:.2f}")
            
            # By underlying
            print(f"\n📈 By Underlying:")
            underlying_summary = short_calls.groupby('underlying').agg({
                'qty': 'sum',
                'premium': 'sum',
                'net_premium': 'sum'
            }).round(2)
            print(underlying_summary)
        
        # Save to CSV
        csv_filename = "short_calls_recent.csv"
        print(f"\n💾 Saving results to {csv_filename}...")
        extractor.save_to_csv(short_calls, csv_filename)
        
        print(f"\n✅ Example usage completed successfully!")
        print(f"📁 Results saved to: {csv_filename}")
        
    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
        print("Please ensure tokens.json exists and run the OAuth flow first.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Please check your API credentials and network connection.")


def demonstrate_advanced_usage():
    """Demonstrate more advanced usage patterns."""
    print("\n" + "=" * 60)
    print("    Advanced Usage Examples")
    print("=" * 60)
    
    try:
        extractor = SchwabTradesExtractor()
        
        # Example 1: Get trades for a specific account
        print("\n1️⃣ Getting trades for specific account...")
        # Note: You would need to know your account ID
        # all_trades = extractor.get_trades_dataframe(start_date, end_date, account_id="your_account_id")
        
        # Example 2: Get trades for a custom date range
        print("\n2️⃣ Getting trades for custom date range...")
        custom_start = datetime(2024, 1, 1)
        custom_end = datetime(2024, 1, 31)
        print(f"   Date range: {custom_start.date()} to {custom_end.date()}")
        
        # Example 3: Filter by specific underlying
        print("\n3️⃣ Filtering by specific underlying...")
        # This would be done after getting the DataFrame:
        # nvda_calls = short_calls[short_calls['underlying'] == 'NVDA']
        
        print("✅ Advanced usage examples completed")
        
    except Exception as e:
        print(f"❌ Error in advanced usage: {e}")


if __name__ == "__main__":
    # Run main example
    main()
    
    # Ask if user wants to see advanced examples
    try:
        show_advanced = input("\n❓ Would you like to see advanced usage examples? (y/n): ").strip().lower()
        if show_advanced in ['y', 'yes']:
            demonstrate_advanced_usage()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception:
        print("\n👋 Example usage completed!")

