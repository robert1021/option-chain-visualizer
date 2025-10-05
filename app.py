from flask import Flask, render_template, request
from flask_caching import Cache
import yfinance as yf
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import math
from datetime import datetime, date
import io
import base64
import sys
import os

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --- App & Cache Initialization ---
app = Flask(__name__, template_folder=resource_path("templates"))

# Configure caching
config = {
    "CACHE_TYPE": "SimpleCache",  # Use a simple in-memory cache
    "CACHE_DEFAULT_TIMEOUT": 300  # Cache results for 5 minutes (300 seconds)
}

app.config.from_mapping(config)
cache = Cache(app)

# Suppress pandas SettingWithCopyWarning
pd.options.mode.chained_assignment = None


# --- Refactored Plotting Logic with Caching ---
@cache.memoize()
def generate_plot(ticker_symbol, option_type):
    """
    Fetches option data and generates a plot, returning it as a Base64 encoded string.
    Results are cached to speed up repeated requests.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        history = ticker.history(period="1d")
        if history.empty:
            return None, f"Invalid or unknown ticker: '{ticker_symbol}'"
        last_price = history['Close'].iloc[-1]

        expiration_dates = ticker.options
        if not expiration_dates:
            return None, f"No option expiration dates found for '{ticker_symbol}'"

    except Exception as e:
        return None, f"An error occurred while fetching ticker data: {e}"

    # Set up the subplot grid
    n_dates = len(expiration_dates)
    n_cols = math.ceil(math.sqrt(n_dates))
    n_rows = math.ceil(n_dates / n_cols)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(20, 15), facecolor='#f4f4f9')
    axes = axes.flatten()

    all_handles, all_labels = [], []
    today = date.today()

    for i, date_str in enumerate(expiration_dates):
        ax = axes[i]
        expiration_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        dte = (expiration_date - today).days

        try:
            option_chain = ticker.option_chain(date_str)
            options_data = getattr(option_chain, option_type)

            if not options_data.empty and options_data['openInterest'].sum() > 0:
                # Plotting
                ax.plot(options_data['strike'], options_data['openInterest'], color='royalblue', label='Open Interest')
                ax.grid(True, linestyle='--', alpha=0.5)
                ax.tick_params(axis='y', labelcolor='royalblue')
                ax.set_facecolor('#ffffff')

                ax2 = ax.twinx()
                ax2.bar(options_data['strike'], options_data['volume'], color='darkorange', alpha=0.6, label='Volume')
                ax2.tick_params(axis='y', labelcolor='darkorange')

                # Highlight ITM/OTM strikes
                itm_color = 'lightgreen'
                otm_color = 'lightcoral'

                if option_type == 'calls':
                    ax.axvspan(0, last_price, alpha=0.2, color=itm_color)
                    ax.axvspan(last_price, ax.get_xlim()[1], alpha=0.2, color=otm_color)
                else:  # Puts
                    ax.axvspan(0, last_price, alpha=0.2, color=otm_color)
                    ax.axvspan(last_price, ax.get_xlim()[1], alpha=0.2, color=itm_color)

                ax.set_title(f"Expiration: {date_str} (DTE: {dte})", fontsize=12)

                if not all_handles:
                    handles1, labels1 = ax.get_legend_handles_labels()
                    handles2, labels2 = ax2.get_legend_handles_labels()
                    all_handles = handles1 + handles2
                    all_labels = labels1 + labels2
            else:
                ax.set_title(f"Expiration: {date_str} (DTE: {dte})\n(No Data)", fontsize=12)
                ax.set_xticks([]);
                ax.set_yticks([])
        except Exception:
            ax.set_title(f"Expiration: {date_str} (DTE: {dte})\n(Error loading data)", fontsize=12)
            ax.set_xticks([]);
            ax.set_yticks([])

    for j in range(n_dates, len(axes)):
        axes[j].axis('off')

    fig.suptitle(
        f'{option_type.capitalize()} Option Open Interest & Volume for {ticker_symbol} (Price: ${last_price:.2f})',
        fontsize=24)
    if all_handles:
        fig.legend(all_handles, all_labels, loc='upper center', bbox_to_anchor=(0.5, 0.95), ncol=2, fontsize=14)
    fig.tight_layout(rect=[0, 0.03, 1, 0.93])
    fig.subplots_adjust(hspace=0.6, wspace=0.4)

    # Convert plot to image string
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)

    return img_base64, None


# --- Flask Routes ---
@app.route('/')
def index():
    """Renders the initial form page."""
    return render_template('index.html')


@app.route('/plot')
def plot():
    """Handles form submission, generates plot, and re-renders the page."""
    ticker = request.args.get('ticker', '').upper().strip()
    option_type = request.args.get('option_type', 'calls')

    if not ticker:
        return render_template('index.html', error="Please enter a ticker symbol.")

    plot_url, error_msg = generate_plot(ticker, option_type)

    if error_msg:
        return render_template('index.html', error=error_msg, ticker=ticker, option_type=option_type)

    return render_template('index.html', plot_url=plot_url, ticker=ticker, option_type=option_type)


if __name__ == '__main__':
    app.run(host='0.0.0.0')