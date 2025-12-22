"""
Schwab Trades Module

This module provides functionality to pull trade data from the Schwab Trader API
and process it for short call analysis. It handles authentication, data extraction,
symbol parsing, and CSV export.

Dependencies:
- schwab-py: Schwab Trader API client
- pandas: Data manipulation
- dateutil: Date parsing utilities
"""

import os
import re
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dateutil import parser as date_parser
from dateutil.tz import gettz
import pytz

try:
    from schwab import auth, client
    from schwab.auth import easy_client
except ImportError:
    raise ImportError(
        "schwab-py is required. Install with: pip install schwab-py"
    )


class SchwabTradesExtractor:
    """
    Main class for extracting and processing trade data from Schwab API.
    """
    
    def __init__(self, tokens_file: str = "tokens.json"):
        """
        Initialize the Schwab API client.
        
        Args:
            tokens_file: Path to the tokens.json file from schwab-py OAuth flow
        """
        self.tokens_file = tokens_file
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Schwab API client using tokens.json."""
        if not os.path.exists(self.tokens_file):
            raise FileNotFoundError(
                f"Tokens file not found: {self.tokens_file}\n"
                "Please run the schwab-py OAuth flow first to generate tokens.json"
            )
        
        try:
            # Load tokens and create client
            self.client = easy_client(
                api_key=os.getenv('SCHWAB_API_KEY'),
                app_secret=os.getenv('SCHWAB_APP_SECRET'),
                redirect_uri=os.getenv('SCHWAB_REDIRECT_URI', 'https://localhost'),
                token_path=self.tokens_file
            )
            print(f"✅ Schwab API client initialized successfully")
        except Exception as e:
            raise Exception(f"Failed to initialize Schwab API client: {str(e)}")
    
    def get_orders(self, start_date: datetime, end_date: datetime, 
                   account_id: Optional[str] = None) -> List[Dict]:
        """
        Retrieve orders from Schwab API between start_date and end_date.
        
        Args:
            start_date: Start date for order retrieval
            end_date: End date for order retrieval
            account_id: Optional account ID to filter orders
            
        Returns:
            List of order dictionaries
        """
        try:
            # Convert to ISO format strings
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            print(f"📡 Fetching orders from {start_str} to {end_str}")
            
            # Get orders using the Schwab API
            orders = self.client.get_orders_by_path(
                account_id=account_id,
                from_entered_time=start_date,
                to_entered_time=end_date,
                status='FILLED'  # Only get filled orders
            )
            
            print(f"✅ Retrieved {len(orders)} orders")
            return orders
            
        except Exception as e:
            print(f"❌ Error fetching orders: {str(e)}")
            return []
    
    def parse_option_symbol(self, symbol: str) -> Dict[str, Union[str, float]]:
        """
        Parse option symbols in both OCC and broker-style formats.
        
        Args:
            symbol: Option symbol string
            
        Returns:
            Dictionary with parsed symbol components
        """
        result = {
            'underlying': '',
            'right': '',
            'strike': 0.0,
            'expiration': '',
            'raw_symbol': symbol
        }
        
        # Handle OCC format: AAPL  250117C00190000
        occ_pattern = r'^([A-Z]+)\s*(\d{6})([CP])(\d{8})$'
        occ_match = re.match(occ_pattern, symbol.replace(' ', ''))
        
        if occ_match:
            underlying, exp_date, right, strike = occ_match.groups()
            
            # Parse expiration date (YYMMDD format)
            year = 2000 + int(exp_date[:2])
            month = int(exp_date[2:4])
            day = int(exp_date[4:6])
            expiration = f"{year:04d}-{month:02d}-{day:02d}"
            
            # Parse strike price (divide by 1000 for OCC format)
            strike_price = float(strike) / 1000.0
            
            result.update({
                'underlying': underlying,
                'right': right,
                'strike': strike_price,
                'expiration': expiration
            })
            return result
        
        # Handle broker-style format: AAPL_2025-01-17_C_190
        broker_pattern = r'^([A-Z]+)_(\d{4}-\d{2}-\d{2})_([CP])_(\d+(?:\.\d+)?)$'
        broker_match = re.match(broker_pattern, symbol)
        
        if broker_match:
            underlying, expiration, right, strike = broker_match.groups()
            
            result.update({
                'underlying': underlying,
                'right': right,
                'strike': float(strike),
                'expiration': expiration
            })
            return result
        
        # If no pattern matches, return raw symbol
        print(f"⚠️  Could not parse symbol: {symbol}")
        return result
    
    def extract_fill_data(self, order: Dict) -> List[Dict]:
        """
        Extract fill data from an order, creating one row per fill.
        
        Args:
            order: Order dictionary from Schwab API
            
        Returns:
            List of fill dictionaries
        """
        fills = []
        
        # Get order-level information
        order_id = order.get('orderId', '')
        order_status = order.get('status', '')
        order_time = order.get('enteredTime', '')
        
        # Parse order time
        try:
            if order_time:
                order_dt = date_parser.parse(order_time)
                # Convert to Chicago time
                chicago_tz = gettz('America/Chicago')
                if order_dt.tzinfo is None:
                    order_dt = order_dt.replace(tzinfo=pytz.UTC)
                order_dt_local = order_dt.astimezone(chicago_tz)
            else:
                order_dt_local = datetime.now()
        except Exception:
            order_dt_local = datetime.now()
        
        # Process order legs
        order_legs = order.get('orderLegCollection', [])
        
        for leg in order_legs:
            instrument = leg.get('instrument', {})
            symbol = instrument.get('symbol', '')
            asset_type = instrument.get('assetType', '')
            
            # Only process option orders
            if asset_type != 'OPTION':
                continue
            
            # Parse option symbol
            option_data = self.parse_option_symbol(symbol)
            
            # Get leg details
            instruction = leg.get('instruction', '')
            quantity = leg.get('quantity', 0)
            
            # Process fills for this leg
            leg_fills = leg.get('fills', [])
            
            for fill in leg_fills:
                fill_quantity = fill.get('quantity', 0)
                fill_price = fill.get('price', 0.0)
                fill_time = fill.get('time', order_time)
                
                # Parse fill time
                try:
                    if fill_time:
                        fill_dt = date_parser.parse(fill_time)
                        if fill_dt.tzinfo is None:
                            fill_dt = fill_dt.replace(tzinfo=pytz.UTC)
                        fill_dt_local = fill_dt.astimezone(gettz('America/Chicago'))
                    else:
                        fill_dt_local = order_dt_local
                except Exception:
                    fill_dt_local = order_dt_local
                
                # Calculate premium and fees
                premium = fill_quantity * fill_price * 100  # Options are per 100 shares
                commission = fill.get('commission', 0.0)
                fees = fill.get('fees', 0.0)
                net_premium = premium - commission - fees
                
                fill_data = {
                    'trade_time_local': fill_dt_local.strftime('%Y-%m-%d %H:%M:%S'),
                    'underlying': option_data['underlying'],
                    'right': option_data['right'],
                    'strike': option_data['strike'],
                    'expiration': option_data['expiration'],
                    'qty': fill_quantity,
                    'fill_price': fill_price,
                    'premium': premium,
                    'commission': commission,
                    'fees': fees,
                    'net_premium': net_premium,
                    'order_id': order_id,
                    'order_status': order_status,
                    'instruction': instruction,
                    'symbol': symbol
                }
                
                fills.append(fill_data)
        
        return fills
    
    def get_trades_dataframe(self, start_date: datetime, end_date: datetime,
                           account_id: Optional[str] = None) -> pd.DataFrame:
        """
        Get all trades as a normalized DataFrame.
        
        Args:
            start_date: Start date for trade retrieval
            end_date: End date for trade retrieval
            account_id: Optional account ID to filter trades
            
        Returns:
            Pandas DataFrame with all trade data
        """
        # Get orders from API
        orders = self.get_orders(start_date, end_date, account_id)
        
        # Extract fill data from all orders
        all_fills = []
        for order in orders:
            fills = self.extract_fill_data(order)
            all_fills.extend(fills)
        
        # Create DataFrame
        if all_fills:
            df = pd.DataFrame(all_fills)
            print(f"✅ Created DataFrame with {len(df)} fills")
        else:
            # Create empty DataFrame with expected columns
            df = pd.DataFrame(columns=[
                'trade_time_local', 'underlying', 'right', 'strike', 'expiration',
                'qty', 'fill_price', 'premium', 'commission', 'fees', 'net_premium',
                'order_id', 'order_status', 'instruction', 'symbol'
            ])
            print("⚠️  No fills found, created empty DataFrame")
        
        return df
    
    def filter_short_calls(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter DataFrame to only include short call sells.
        
        Args:
            df: Input DataFrame with trade data
            
        Returns:
            Filtered DataFrame with only short call sells
        """
        if df.empty:
            return df
        
        # Filter for short call sells: SELL instruction and CALL right
        short_calls = df[
            (df['instruction'] == 'SELL') & 
            (df['right'] == 'C')
        ].copy()
        
        print(f"📊 Found {len(short_calls)} short call sells out of {len(df)} total fills")
        return short_calls
    
    def save_to_csv(self, df: pd.DataFrame, filename: str = "short_calls_recent.csv"):
        """
        Save DataFrame to CSV file.
        
        Args:
            df: DataFrame to save
            filename: Output filename
        """
        try:
            df.to_csv(filename, index=False)
            print(f"✅ Saved {len(df)} records to {filename}")
        except Exception as e:
            print(f"❌ Error saving to CSV: {str(e)}")
    
    def get_short_calls(self, start_date: datetime, end_date: datetime,
                       account_id: Optional[str] = None,
                       save_csv: bool = True,
                       csv_filename: str = "short_calls_recent.csv") -> pd.DataFrame:
        """
        Main method to get short calls and optionally save to CSV.
        
        Args:
            start_date: Start date for trade retrieval
            end_date: End date for trade retrieval
            account_id: Optional account ID to filter trades
            save_csv: Whether to save results to CSV
            csv_filename: Filename for CSV output
            
        Returns:
            DataFrame with short call sells
        """
        print(f"🔍 Extracting short calls from {start_date.date()} to {end_date.date()}")
        
        # Get all trades
        all_trades = self.get_trades_dataframe(start_date, end_date, account_id)
        
        # Filter for short calls
        short_calls = self.filter_short_calls(all_trades)
        
        # Save to CSV if requested
        if save_csv and not short_calls.empty:
            self.save_to_csv(short_calls, csv_filename)
        
        return short_calls


def main():
    """
    Example usage of the SchwabTradesExtractor class.
    """
    # Initialize extractor
    try:
        extractor = SchwabTradesExtractor()
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return
    
    # Get trades for the past 7 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    print(f"📅 Fetching trades from {start_date.date()} to {end_date.date()}")
    
    # Get short calls
    short_calls = extractor.get_short_calls(
        start_date=start_date,
        end_date=end_date,
        save_csv=True
    )
    
    # Display results
    if not short_calls.empty:
        print(f"\n📊 Short Calls Summary:")
        print(f"Total short calls: {len(short_calls)}")
        print(f"\nFirst few records:")
        print(short_calls.head().to_string(index=False))
        
        # Summary statistics
        if len(short_calls) > 0:
            total_premium = short_calls['premium'].sum()
            total_commission = short_calls['commission'].sum()
            total_fees = short_calls['fees'].sum()
            net_premium = short_calls['net_premium'].sum()
            
            print(f"\n💰 Financial Summary:")
            print(f"Total Premium: ${total_premium:.2f}")
            print(f"Total Commission: ${total_commission:.2f}")
            print(f"Total Fees: ${total_fees:.2f}")
            print(f"Net Premium: ${net_premium:.2f}")
    else:
        print("📭 No short calls found in the specified date range")


if __name__ == "__main__":
    main()

