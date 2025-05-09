# File: controllers/portfolio_study_controller.py

import numpy as np
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
from PySide6.QtWidgets import (QMessageBox, QTableWidgetItem, QLabel, QSlider, 
                               QWidget, QVBoxLayout, QTabWidget)
from PySide6.QtCore import Qt
import logging

logger = logging.getLogger(__name__)

class PortfolioStudyController:
    """
    Enhanced controller for portfolio study functionality.
    Provides efficient data retrieval and visualisation using pre-calculated metrics.
    """
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.view = None
        self.current_portfolio = None
        self.data = None
    
    def set_view(self, view):
        """
        Set the view and connect signals.
        
        Args:
            view: PortfolioStudyView instance to be controlled
        """
        self.view = view
        self.view.set_controller(self)
        self.view.update_plot.connect(self.analyse_portfolio)
    
    def set_portfolio(self, portfolio):
        """Set the current portfolio."""
        self.current_portfolio = portfolio
        if self.view:
            self.view.update_portfolio_stocks(portfolio.stocks.values())

    def get_portfolio_data(self, params):
        """
        Get portfolio metrics data based on study parameters.
        
        Args:
            params: Dictionary containing analysis parameters
                
        Returns:
            pd.DataFrame: DataFrame containing requested metrics
        """
        try:
            # Get unique fields for the query
            fields = ['date']  # Always include date

            # Map study types to database columns
            study_type_mapping = {
                'market_value': ['market_value'],  # Changed to list for consistency
                'profitability': ['total_return', 'market_value', 'daily_pl', 'daily_pl_pct', 'total_return_pct', 'cumulative_return_pct'],
                'dividend_performance': ['cash_dividend', 'cash_dividends_total', 'drp_share', 'drp_shares_total', 'close_price']
            }
            
            # Always include market_value for distribution charts
            fields.append('market_value')
            
            # Add required fields based on study type
            if params['study_type'] in study_type_mapping:
                study_fields = study_type_mapping[params['study_type']]
                fields.extend(study_fields)
                    
            # Add any specific metric if provided
            if 'metric' in params:
                if isinstance(params['metric'], list):
                    fields.extend(params['metric'])
                else:
                    fields.append(params['metric'])
                    
            if 'metrics' in params:
                fields.extend(params['metrics'])

            # Remove any duplicates while preserving order
            fields = list(dict.fromkeys(fields))
            
            # Build query using the ordered fields
            query = f"""
                    SELECT {', '.join(fields)}
                    FROM final_metrics
                    WHERE stock_id = :stock_id 
                    AND date BETWEEN :start_date AND :end_date
                    ORDER BY date
                """
            logger.debug(f"Generated SQL query: {query}")
            logger.debug(f"Fields being queried: {fields}")  # Added debug logging
            
            # Get data for selected stocks
            data_frames = []
            for yahoo_symbol in params['selected_stocks']:
                stock = self.current_portfolio.get_stock(yahoo_symbol)
                if stock:
                    query_params = {
                        'stock_id': stock.id,
                        'start_date': params['start_date'],
                        'end_date': params['end_date']
                    }
                    
                    logger.debug(f"Executing query for stock {yahoo_symbol} with params: {query_params}")
                    results = self.db_manager.fetch_all_with_params(query, query_params)
                    
                    if results:
                        df = pd.DataFrame(results, columns=fields)
                        df['stock'] = yahoo_symbol
                        data_frames.append(df)
            
            if data_frames:
                return pd.concat(data_frames, ignore_index=True)
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Error getting portfolio data: {str(e)}")
            logger.error(f"Parameters received: {params}")
            raise

    def calculate_portfolio_total_metrics(self, data, params):
        """Calculate portfolio-wide metrics."""
        if params['chart_type'] == 'dollar_value':
            # Simple sum for dollar values
            return data.groupby('date')['total_return'].sum().reset_index()
        else:  # percentage
            # Calculate weighted return
            grouped = data.groupby('date').agg({
                'total_return': 'sum',
                'market_value': 'sum'
            }).reset_index()
            grouped['value'] = grouped['total_return'] / grouped['market_value'] * 100
            return grouped

    def calculate_deltas(self, data, params):
        """Calculate day-over-day changes."""
        if params['view_type'] == 'individual_stocks':
            # Calculate deltas for each stock
            for stock in data['stock'].unique():
                mask = data['stock'] == stock
                base_col = params['metric'].replace('_delta', '')
                data.loc[mask, 'value'] = data.loc[mask, base_col].diff()
        else:
            # Calculate deltas for portfolio total
            data['value'] = data['value'].diff()
        
        return data

    def analyse_portfolio(self, params):
        """
        Analyse portfolio based on given parameters and update views.
        
        Args:
            params: Dictionary containing analysis parameters
        """
        try:

            # Clean up any existing distribution widgets before proceeding
            self.cleanup_distribution_widgets()

            # Get data based on study type
            self.data = self.get_portfolio_data(params)
            
            if self.data.empty:
                QMessageBox.warning(
                    self.view,
                    "No Data",
                    "No data available for the selected stocks and date range."
                )
                return
            
            # Update plot based on study type
            self.view.figure.clear()
            ax = self.view.figure.add_subplot(111)
            
            study_type = params['study_type']
            
            if study_type == "market_value":
                self.plot_market_value(ax, params)
            elif study_type == "profitability":
                self.plot_profitability(ax, params)
            elif study_type == "dividend_performance":
                self.plot_dividends(ax, params)
            else:  # Portfolio Distribution
                self.plot_distribution(ax)
            
            # Update statistics
            self.update_statistics_table(params)
            
            # Refresh canvases
            self.view.figure.tight_layout()
            self.view.canvas.draw()
            
        except Exception as e:
            logger.error(f"Error in portfolio analysis: {str(e)}")
            QMessageBox.warning(
                self.view,
                "Analysis Error",
                f"Failed to analyse portfolio: {str(e)}"
            )

    def setup_date_axis(self, ax):
        """
        Configure date axis formatting and ticks.
        
        Args:
            ax: The matplotlib axis to configure
        """
        from matplotlib.dates import AutoDateLocator
        import matplotlib.dates as mdates
        
        # Create locator and formatter for smart date tick handling
        locator = AutoDateLocator(minticks=3, maxticks=7)
        formatter = mdates.ConciseDateFormatter(locator)
        
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
        
        # Rotate labels
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
        
        # Adjust the subplot parameters for the current figure
        plt.gcf().tight_layout()

    def plot_market_value(self, ax, params):
        """
        Plot market value analysis with proper handling of weekend/holiday data.
        Uses forward fill to maintain last known values for non-trading days.
        
        Args:
            ax: Matplotlib axis object for plotting
            params: Dictionary containing plot parameters including view_type and chart_type
        """
        # Add debug logging
        logger.debug(f"Market Value plot parameters: {params}")
        
        # Create a copy of the data to avoid modifying the original
        plot_data = self.data.copy()
        
        # Convert date column to datetime if not already
        plot_data['date'] = pd.to_datetime(plot_data['date'])
        
        # Set multi-index using both date and stock
        plot_data.set_index(['date', 'stock'], inplace=True)
        
        # Unstack to get stock as columns, then resample to daily frequency and forward fill
        plot_data = plot_data['market_value'].unstack()
        plot_data = plot_data.asfreq('D').ffill()
        
        # Create a list to store the lines and labels
        lines = []
        labels = []
        
        # Check view type using the correct mapped value
        if params['view_type'] == "individual_stocks":
            # Plot individual stock values
            for stock in params['selected_stocks']:
                if stock in plot_data.columns:
                    line = ax.plot(plot_data.index, plot_data[stock], 
                        label=stock, linewidth=1.5, alpha=0.7)[0]  # Get the Line2D object
                    lines.append(line)
                    labels.append(stock)
                        
        else:  # Portfolio Total
            # Check chart type using the correct mapped value
            if params['chart_type'] == "line_chart":
                # Sum market values by date using the forward-filled values
                portfolio_total = plot_data.sum(axis=1)
                line = ax.plot(plot_data.index, portfolio_total.values,
                    label='Total Portfolio', linewidth=2, alpha=0.7)[0]
                lines.append(line)
                labels.append('Total Portfolio')
            elif params['chart_type'] == "stacked_area": # This should match the value in config.yaml
                # Fill any remaining NaN values with 0 for stacking
                plot_data = plot_data.fillna(0)
                
                # Ensure all stocks are properly aligned
                sorted_columns = sorted(plot_data.columns)
                plot_data = plot_data[sorted_columns]
                
                # Create the stacked area plot
                ax.stackplot(plot_data.index, 
                            [plot_data[col] for col in plot_data.columns],
                            labels=plot_data.columns,
                            alpha=0.8)
            
        ax.set_title("Portfolio Market Value Over Time")
        ax.set_xlabel("Date")
        ax.set_ylabel("Value ($)")
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.grid(True, alpha=0.3)
        
        # Set up date axis
        self.setup_date_axis(ax)
        
        # Format y-axis to use comma separator for thousands
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))

        # Set up line picking after the plot is created
        self.view.setup_line_picking(lines, labels)

    def plot_profitability(self, ax, params):
        """
        Plot profitability analysis with proper date axis formatting.
        Supports zeroing values at start date for cumulative views.
        Handles weekend/holiday data using forward fill.
        Uses forward fill to maintain last known values for non-trading days.
        
        Return Calculations:
        - Total Return $: Simple sum of profits/losses in dollar terms
        - Total Return %: Return as percentage of total invested capital (affected by new investments)
        - Aggregated ROI %: Time-weighted return using geometric mean (not affected by new investments)

        Args:
            ax: matplotlib axis object for plotting
            params: Dictionary containing plot parameters including view_type and chart_type
        """
        try:
            view_type = params['view_type']
            time_period = params['calculation_type']  # 'daily' or 'cumulative'
            chart_type = params['chart_type']
            zero_at_start = params.get('zero_at_start', False)
            
            # Convert dates to datetime if they aren't already
            self.data['date'] = pd.to_datetime(self.data['date'])
            
            # Determine which metric to use
            if chart_type == 'dollar_value':
                metric = 'daily_pl' if time_period == 'daily' else 'total_return'
                ylabel = "Return ($)"
                value_format = lambda x, p: f'${x:,.0f}'
            elif chart_type == 'percentage':
                metric = 'daily_pl_pct' if time_period == 'daily' else 'total_return_pct'
                ylabel = "Return (%)"
                value_format = lambda x, p: f'{x:.1f}%'
            else:  # aggregated_percentage
                metric = 'cumulative_return_pct'
                ylabel = "Return (%)"
                value_format = lambda x, p: f'{x:.1f}%'
            
            # Create lists to store lines and labels
            lines = []
            labels = []
            
            if view_type == 'individual_stocks':
                for stock in params['selected_stocks']:
                    stock_data = self.data[self.data['stock'] == stock].copy()
                    y_values = stock_data[metric]
                    
                    # Zero at start date if requested
                    if zero_at_start and time_period == 'cumulative':
                        start_value = y_values.iloc[0]
                        y_values = y_values - start_value
                        
                    line = ax.plot(stock_data['date'], y_values, label=stock, linewidth=1.5, alpha=0.7)[0]
                    lines.append(line)
                    labels.append(stock)

            else:  # portfolio_total
                if time_period == 'cumulative' and chart_type == 'dollar_value':
                    # Create a copy of the data to avoid modifying original
                    plot_data = self.data.copy()
                    
                    # Set multi-index using date and stock
                    plot_data.set_index(['date', 'stock'], inplace=True)
                    
                    # Unstack to get stock as columns
                    plot_data = plot_data[metric].unstack()
                    
                    # Resample to daily frequency and forward fill
                    plot_data = plot_data.asfreq('D').ffill()
                    
                    # Calculate portfolio total using the forward-filled values
                    y_values = plot_data.sum(axis=1)
                    
                    # Zero at start date if requested
                    if zero_at_start:
                        start_value = y_values.iloc[0]
                        y_values = y_values - start_value
                    
                    line = ax.plot(y_values.index, y_values.values, label='Portfolio Total', 
                                linewidth=2, alpha=0.7)[0]
                    lines.append(line)
                    labels.append('Portfolio Total')
                
                # For portfolio total, percentage calculations
                elif chart_type == 'percentage':
                    if time_period == 'daily':
                        # For daily changes, sum daily_pl and express as % of total portfolio value
                        grouped = self.data.groupby('date').agg({
                            'daily_pl': 'sum',
                            'market_value': 'sum'
                        })
                        y_values = (grouped['daily_pl'] / grouped['market_value']) * 100
                    else:  # cumulative
                        # Handle weekend data for cumulative percentage return
                        plot_data = self.data.copy()
                        plot_data.set_index(['date', 'stock'], inplace=True)
                        
                        # Get required columns and unstack
                        total_return_data = plot_data['total_return'].unstack()
                        market_value_data = plot_data['market_value'].unstack()
                        
                        # Resample and forward fill both
                        total_return_data = total_return_data.asfreq('D').ffill()
                        market_value_data = market_value_data.asfreq('D').ffill()
                        
                        # Calculate portfolio percentage return
                        portfolio_total_return = total_return_data.sum(axis=1)
                        portfolio_total_value = market_value_data.sum(axis=1)
                        y_values = (portfolio_total_return / portfolio_total_value) * 100
                        
                    # Zero at start date if requested
                    if zero_at_start and time_period == 'cumulative':
                        start_value = y_values.iloc[0]
                        y_values = y_values - start_value
                        
                    # Use y_values.index instead of grouped.index
                    line = ax.plot(y_values.index, y_values.values, label='Portfolio Total', 
                                linewidth=2, alpha=0.7)[0]
                    lines.append(line)
                    labels.append('Portfolio Total')
                
            # Add zero line for reference
            ax.axhline(y=0, color='r', linestyle='--', alpha=0.3)

            # Update ylabel if zeroed at start
            if zero_at_start and time_period == 'cumulative':
                ylabel = f"Change in {ylabel} from Start Date"
                
            # Set axis limits based on actual data range
            min_date = self.data['date'].min()
            max_date = self.data['date'].max()
            ax.set_xlim(min_date, max_date)
            
            period_type = 'Daily' if time_period == 'daily' else 'Cumulative'
            ax.set_title(f"Portfolio {period_type} Returns" + 
                    (" (Change from Start Date)" if zero_at_start else ""))
            ax.set_xlabel("Date")
            ax.set_ylabel(ylabel)
            ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
            ax.grid(True, alpha=0.3)
            
            # Format axes
            self.setup_date_axis(ax)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(value_format))
            
            # Set up line picking
            self.view.setup_line_picking(lines, labels)
            
        except Exception as e:
            logger.error(f"Error plotting profitability: {str(e)}")
            logger.exception("Detailed traceback:")
            raise

    def plot_dividends(self, ax, params):
        """
        Plot dividend analysis with all values represented in dollars.
        Handles individual stocks and portfolio totals, showing either cash dividends,
        DRP value, or total dividend value (cash + DRP combined).
        
        The method supports:
        - Daily or cumulative views
        - Individual stock or portfolio total analysis
        - Cash dividends, DRP (converted to dollar value), or combined total
        
        Args:
            ax: matplotlib axis object for plotting
            params: Dictionary containing:
                - chart_type: 'cash', 'drp', or 'combined'
                - time_period: 'daily' or 'cumulative'
                - view_type: 'individual_stocks' or 'portfolio_total'
        """
        try:
            logger.debug(f"Plotting dividends with parameters: {params}")
            
            # Create a copy of the data to avoid modifying original
            plot_data = self.data.copy()
            
            # Convert date column to datetime if not already
            plot_data['date'] = pd.to_datetime(plot_data['date'])
            
            # Calculate DRP value in dollars before setting index
            if params['chart_type'] in ['drp', 'combined']:
                # Convert DRP shares to dollar values using closing price
                plot_data['drp_value'] = plot_data['drp_share'] * plot_data['close_price']
                plot_data['drp_value_total'] = plot_data['drp_shares_total'] * plot_data['close_price']
            
            # Set multi-index using both date and stock
            plot_data.set_index(['date', 'stock'], inplace=True)
            
            # Create lists to store lines and labels
            lines = []
            labels = []
            
            # Handle data based on chart type
            if params['chart_type'] == 'cash':
                # For cash dividends, use appropriate metric based on time period
                metric = 'cash_dividends_total' if params['time_period'] == 'cumulative' else 'cash_dividend'
                plot_data = plot_data[metric].unstack()
                ylabel = "Cash Dividend Value ($)"
                value_format = lambda x, p: f'${x:,.2f}'
                
            elif params['chart_type'] == 'drp':
                # For DRP, use calculated dollar values instead of share counts
                metric = 'drp_value_total' if params['time_period'] == 'cumulative' else 'drp_value'
                plot_data = plot_data[metric].unstack()
                ylabel = "DRP Value ($)"
                value_format = lambda x, p: f'${x:,.2f}'
                
            else:  # combined view
                # Get both cash and DRP data
                if params['time_period'] == 'cumulative':
                    cash_data = plot_data['cash_dividends_total'].unstack()
                    drp_data = plot_data['drp_value_total'].unstack()
                else:
                    cash_data = plot_data['cash_dividend'].unstack()
                    drp_data = plot_data['drp_value'].unstack()
                
                # Combine cash and DRP values into total dividend value
                total_dividend_data = cash_data.fillna(0) + drp_data.fillna(0)
                ylabel = "Total Dividend Value ($)"
                value_format = lambda x, p: f'${x:,.2f}'

            # For cumulative views, resample to daily frequency and forward fill
            if params['time_period'] == 'cumulative':
                if params['chart_type'] == 'combined':
                    total_dividend_data = total_dividend_data.asfreq('D').ffill()
                else:
                    plot_data = plot_data.asfreq('D').ffill()

            # Create visualization based on view type
            if params['view_type'] == 'individual_stocks':
                if params['chart_type'] == 'combined':
                    # Plot total dividend value for each stock
                    for stock in total_dividend_data.columns:
                        line = ax.plot(total_dividend_data.index, total_dividend_data[stock],
                            label=stock, linewidth=1.5, alpha=0.7)[0]
                        lines.append(line)
                        labels.append(stock)
                else:
                    # Plot individual metric for each stock
                    for stock in plot_data.columns:
                        line = ax.plot(plot_data.index, plot_data[stock],
                            label=stock, linewidth=1.5, alpha=0.7)[0]
                        lines.append(line)
                        labels.append(stock)
                        
            else:  # portfolio_total
                if params['chart_type'] == 'combined':
                    # Calculate and plot portfolio total dividend value
                    portfolio_total = total_dividend_data.sum(axis=1)
                    line = ax.plot(portfolio_total.index, portfolio_total.values,
                        label='Total Dividends', linewidth=2, alpha=0.7)[0]
                    lines.append(line)
                    labels.append('Total Dividends')
                else:
                    # Calculate and plot portfolio total for single metric
                    portfolio_total = plot_data.sum(axis=1)
                    line = ax.plot(portfolio_total.index, portfolio_total.values,
                        label='Portfolio Total', linewidth=2, alpha=0.7)[0]
                    lines.append(line)
                    labels.append('Portfolio Total')

            # Set title and labels
            period_type = 'Cumulative' if params['time_period'] == 'cumulative' else 'Daily'
            chart_name = {
                'cash': 'Cash Dividends',
                'drp': 'DRP Value',
                'combined': 'Total Dividend Value'
            }[params['chart_type']]
            
            ax.set_title(f"{period_type} {chart_name}")
            ax.set_xlabel("Date")
            ax.set_ylabel(ylabel)
            
            # Format y-axis to show dollar values
            ax.yaxis.set_major_formatter(plt.FuncFormatter(value_format))
            
            # Set up date axis consistently with other plots
            self.setup_date_axis(ax)
            
            # Add legend with proper positioning
            ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
            
            # Adjust layout to prevent label cutoff
            plt.tight_layout()
            
            # Set up line picking
            self.view.setup_line_picking(lines, labels)
            
        except Exception as e:
            logger.error(f"Error plotting dividends: {str(e)}")
            logger.exception("Detailed traceback:")
            raise

    def plot_distribution(self, ax):
        """
        Plot portfolio distribution pie chart with an interactive time slider.
        The slider allows users to view portfolio distribution changes over time.
        Handles missing weekend/holiday data using forward fill.
        
        Args:
            ax: matplotlib axis object for the pie chart
        """
        try:
            # Convert dates to datetime if needed
            self.data['date'] = pd.to_datetime(self.data['date'])

            # Create a copy of the data to avoid modifying original
            plot_data = self.data.copy()
            
            # Set multi-index using date and stock, then unstack
            plot_data.set_index(['date', 'stock'], inplace=True)
            plot_data = plot_data['market_value'].unstack()
            
            # Resample to daily frequency and forward fill missing values
            plot_data = plot_data.asfreq('D').ffill()
            
            # Get all unique dates after forward filling
            unique_dates = sorted(plot_data.index)
            
            if len(unique_dates) == 0:
                ax.text(0.5, 0.5, 'No data available for selected date range',
                    ha='center', va='center')
                return
            
            # Find the charts tab and its layout
            charts_tab = None
            for i in range(self.view.findChild(QTabWidget).count()):
                if self.view.findChild(QTabWidget).tabText(i) == "Charts":
                    charts_tab = self.view.findChild(QTabWidget).widget(i)
                    break
            
            if not charts_tab:
                logger.error("Could not find Charts tab")
                return
                
            # Create a container for our date controls
            date_container = QWidget()
            date_layout = QVBoxLayout(date_container)
            date_layout.setContentsMargins(10, 0, 10, 10)  # Add some padding
            
            # Create total value label
            total_value_label = QLabel()
            total_value_label.setAlignment(Qt.AlignCenter)
            total_value_label.setStyleSheet("QLabel { font-size: 12pt; margin: 2px; }")
            date_layout.addWidget(total_value_label)
            
            # Create slider with some styling
            time_slider = QSlider(Qt.Horizontal)
            time_slider.setMinimum(0)
            time_slider.setMaximum(len(unique_dates) - 1)
            time_slider.setTickPosition(QSlider.TicksBelow)
            time_slider.setTickInterval(max(1, len(unique_dates) // 10))
            time_slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    border: 1px solid #999999;
                    height: 8px;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B1B1B1, stop:1 #c4c4c4);
                    margin: 2px 0;
                }
                QSlider::handle:horizontal {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b4b4b4, stop:1 #8f8f8f);
                    border: 1px solid #5c5c5c;
                    width: 18px;
                    margin: -2px 0;
                    border-radius: 3px;
                }
            """)
            date_layout.addWidget(time_slider)
            
            # Add the date container to the charts tab layout
            charts_tab.layout().addWidget(date_container)
            
            def update_distribution(position):
                """Update the pie chart for the selected date position."""
                ax.clear()
                
                # Get current date
                current_date = unique_dates[position]
                
                # Get data for current date from the forward-filled dataset
                current_data = plot_data.loc[current_date]
                
                # Calculate total portfolio value
                total_portfolio_value = current_data.sum()
                total_value_label.setText(f"Total Portfolio Value: ${total_portfolio_value:,.2f}")
                
                # Filter out zero values
                positive_sizes = current_data[current_data > 0]
                
                if not positive_sizes.empty:
                    # Create labels with stock name and value
                    labels = [f"{stock}\n(${value:,.0f})" for stock, value in positive_sizes.items()]
                    
                    # Create pie chart
                    wedges, texts, autotexts = ax.pie(
                        positive_sizes,
                        labels=labels,
                        autopct='%1.1f%%',
                        pctdistance=0.85,
                        startangle=90,
                        wedgeprops={'edgecolor': 'white', 'linewidth': 1}
                    )
                    
                    ax.set_title(f"Portfolio Distribution on {current_date.strftime('%Y-%m-%d')}")
                    plt.setp(autotexts, color='white', fontsize=8, weight='bold')
                    plt.setp(texts, fontsize=8)
                else:
                    ax.text(0.5, 0.5, 'No positive market values to display',
                        ha='center', va='center')
                
                self.view.canvas.draw()
            
            # Connect slider to update function
            time_slider.valueChanged.connect(update_distribution)
            
            # Initial plot
            update_distribution(0)
            
            # Store references for cleanup
            self.date_container = date_container
            
        except Exception as e:
            logger.error(f"Error creating distribution chart: {str(e)}")
            logger.exception("Detailed traceback:")
            ax.text(0.5, 0.5, 'Error creating distribution chart',
                ha='center', va='center')
            raise

    def cleanup_distribution_widgets(self):
        """Remove the time slider and date label when switching views or closing."""
        if hasattr(self, 'date_container'):
            self.date_container.deleteLater()
            delattr(self, 'date_container')

    def setup_date_axis(self, ax):
        """
        Configure date axis formatting and ticks.
        
        Args:
            ax: The matplotlib axis to configure
        """
        from matplotlib.dates import AutoDateLocator
        import matplotlib.dates as mdates
        
        # Create locator and formatter for smart date tick handling
        locator = AutoDateLocator(minticks=3, maxticks=7)
        formatter = mdates.ConciseDateFormatter(locator)
        
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
        
        # Rotate labels for better readability
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
        
        # Get current figure
        fig = plt.gcf()
        
        # Use a tight layout to prevent label cutoff
        fig.tight_layout()

    def update_statistics_table(self, params):
        """Update statistics table with current analysis."""
        study_type = params['study_type']
        
        # Clear existing stats
        self.view.stats_table.setRowCount(0)
        stats = {}
        
        if study_type == "Market Value":
            latest_values = self.data.groupby('stock')['market_value'].last()
            total_value = latest_values.sum()
            
            stats.update({
                'Total Portfolio Value': f"${total_value:,.2f}",
                'Number of Holdings': str(len(latest_values)),
                'Largest Holding': f"{latest_values.idxmax()} (${latest_values.max():,.2f})",
                'Smallest Holding': f"{latest_values.idxmin()} (${latest_values.min():,.2f})"
            })
            
        elif study_type == "Profitability":
            if params['display_type'] == "Percentage":
                metric = 'daily_pl_pct' if params['time_period'] == "Daily Changes" else 'total_return_pct'
                suffix = "%"
            else:
                metric = 'daily_pl' if params['time_period'] == "Daily Changes" else 'total_return'
                suffix = "$"
            
            data = self.data[metric]
            stats.update({
                'Average Return': f"{data.mean():.2f}{suffix}",
                'Best Return': f"{data.max():.2f}{suffix}",
                'Worst Return': f"{data.min():.2f}{suffix}",
                'Volatility': f"{data.std():.2f}{suffix}"
            })
            
        elif study_type == "Dividend Performance":
            if params['view_type'] == "Cash Dividends":
                total_col = 'cash_dividends_total'
                period_col = 'cash_dividend'
                prefix = "$"
            else:
                total_col = 'drp_shares_total'
                period_col = 'drp_share'
                prefix = ""
            
            stats.update({
                'Total Received': f"{prefix}{self.data[total_col].max():.2f}",
                'Average Per Period': f"{prefix}{self.data[period_col].mean():.2f}",
                'Largest Single Payment': f"{prefix}{self.data[period_col].max():.2f}",
                'Number of Payments': str(len(self.data[self.data[period_col] > 0]))
            })
            
        else:  # Portfolio Distribution
            latest_date = self.data['date'].max()
            latest_values = self.data[self.data['date'] == latest_date]
            holdings = latest_values.groupby('stock')['market_value'].sum()
            
            stats.update({
                'Number of Holdings': str(len(holdings)),
                'Total Portfolio Value': f"${holdings.sum():,.2f}",
                'Largest Allocation': f"{holdings.idxmax()} ({holdings.max()/holdings.sum()*100:.1f}%)",
                'Smallest Allocation': f"{holdings.idxmin()} ({holdings.min()/holdings.sum()*100:.1f}%)"
            })
        
        # Update table
        self.view.stats_table.setRowCount(len(stats))
        for i, (metric, value) in enumerate(stats.items()):
            self.view.stats_table.setItem(i, 0, QTableWidgetItem(metric))
            self.view.stats_table.setItem(i, 1, QTableWidgetItem(str(value)))

    def get_active_stocks_for_date_range(self, start_date, end_date, dividend_type=None):
        """
        Get stocks that have at least one non-zero market value within the date range.
        Uses the portfolio_stocks linking table to find stocks associated with the current portfolio.
        
        Args:
            start_date (datetime): Start date for filtering
            end_date (datetime): End date for filtering
                
        Returns:
            list: List of stock objects that have market activity in the date range
        """
        try:
            logger.debug(f"Fetching active stocks between {start_date} and {end_date}")
            logger.debug(f"Current portfolio ID: {self.current_portfolio.id}")
            logger.debug(f"Dividend type filter: {dividend_type}")
            
            # Base query for non-dividend analysis
            base_query = """
                WITH stock_activity AS (
                    SELECT 
                        s.id,
                        s.yahoo_symbol,
                        s.name,
                        COUNT(*) as total_days,
                        SUM(CASE WHEN fm.market_value > 0 THEN 1 ELSE 0 END) as active_days,
                        MAX(fm.market_value) as max_value
                """
            
            # Add dividend-specific metrics based on type
            if dividend_type == 'cash':
                base_query += """,
                        SUM(CASE WHEN fm.cash_dividend > 0 THEN 1 ELSE 0 END) as dividend_days
                """
            elif dividend_type == 'drp':
                base_query += """,
                        SUM(CASE WHEN fm.drp_share > 0 THEN 1 ELSE 0 END) as dividend_days
                """
            elif dividend_type == 'combined':
                base_query += """,
                        SUM(CASE WHEN fm.cash_dividend > 0 OR fm.drp_share > 0 THEN 1 ELSE 0 END) as dividend_days
                """
                
            # Complete the query
            query = base_query + """
                    FROM stocks s
                    JOIN portfolio_stocks ps ON s.id = ps.stock_id
                    JOIN final_metrics fm ON s.id = fm.stock_id
                    WHERE fm.date BETWEEN :start_date AND :end_date
                    AND ps.portfolio_id = :portfolio_id
                    GROUP BY s.id, s.yahoo_symbol, s.name
                )
                SELECT 
                    id,
                    yahoo_symbol,
                    name,
                    total_days,
                    active_days,
                    max_value
            """
            
            # Add dividend filtering if needed
            if dividend_type:
                query += """
                FROM stock_activity
                WHERE dividend_days > 0
                """
            else:
                query += """
                FROM stock_activity
                WHERE active_days > 0
                """
                
            query += " ORDER BY yahoo_symbol;"
            
            params = {
                'start_date': start_date,
                'end_date': end_date,
                'portfolio_id': self.current_portfolio.id
            }
            
            logger.debug(f"Executing query with params: {params}")
            results = self.db_manager.fetch_all_with_params(query, params)
            logger.debug(f"Query returned {len(results)} results")
            
            # Convert results to stock objects
            active_stocks = []
            for row in results:
                stock = self.current_portfolio.get_stock(row[1])  # row[1] is yahoo_symbol
                if stock:
                    active_stocks.append(stock)
                    logger.debug(f"Added stock {stock.yahoo_symbol} to active stocks list")
                else:
                    logger.warning(f"Stock {row[1]} found in database but not in portfolio")
            
            logger.debug(f"Returning {len(active_stocks)} active stocks")
            return active_stocks
                
        except Exception as e:
            logger.error(f"Error getting active stocks: {str(e)}")
            logger.exception("Detailed traceback:")
            return []
    
    def get_view(self):
        """Return the view instance."""
        return self.view