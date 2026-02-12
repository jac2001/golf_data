# 🎯 Golf Prediction Dashboard Guide

## Overview

Interactive web dashboard for running predictions and analyzing results without using command line.

**Features**:
- ✅ Run predictions with simple form
- ✅ View and filter results
- ✅ Interactive charts and visualizations
- ✅ Player search
- ✅ Season performance tracking
- ✅ System status monitoring

---

## Quick Start

### Launch Dashboard

```bash
cd /Users/jacklegnon/Desktop/golf_data
./launch_dashboard.sh
```

Or manually:
```bash
streamlit run dashboard.py
```

The dashboard will open in your browser at `http://localhost:8501`

---

## Dashboard Pages

### 1. 🎯 Run Predictions

**Purpose**: Generate predictions for upcoming tournaments

**Inputs**:
- **ESPN Tournament ID**: From ESPN leaderboard URL
- **Tournament Name**: Official name (e.g., "American Express")
- **Purse**: Total prize money
- **Tournament Type**: Standard/Signature/Major
- **SG Method**: How to calculate recent form
- **Top N**: Number of recommendations to show

**Output**:
- Top 10 picks table
- Download buttons for CSV and picks report
- Command output log

**Example**:
```
ESPN ID: 401811929
Name: American Express
Purse: $9,600,000
Type: Standard
SG Method: last_5
Top N: 20
```

Click **"Run Predictions"** and wait 1-2 minutes.

---

### 2. 📊 View Results

**Purpose**: Analyze previously generated predictions

**Features**:

#### Summary Statistics
- Total players in field
- Average EV
- Maximum EV
- Players with course history

#### Tabs

**🏆 Top Picks**
- Top 20 players by expected value
- Formatted probabilities and stats
- Course history indicators

**📊 Full List**
- Sortable table of all players
- Filters:
  - Minimum EV
  - Minimum win probability
  - Only players with course history

**📈 Charts**
Four visualization options:
1. **EV Distribution** - Histogram showing spread of expected values
2. **Win Probability** - Bar chart of top 30 win probabilities
3. **Recent Form vs EV** - Scatter plot showing correlation
4. **Course History Impact** - Box plot comparing players with/without history

**🔍 Player Search**
- Search by name
- Detailed stats card for each player
- Win/Top-5/Top-10 probabilities
- Recent form (SG Total)
- Course history

---

### 3. 📈 Analytics

**Purpose**: Track your fantasy league performance over the season

**Setup**:
1. Click "Create Season Log" on first visit
2. After each tournament, manually add results to `outputs/season_log.csv`

**Season Log Format**:
```csv
week,date,tournament,pick1,pick2,pick3,result1,result2,result3,points,league_rank,notes
1,2026-01-25,American Express,Scheffler,Brennan,Griffin,1st,T45,T18,150,3/50,"Scheffler won!"
```

**Displays**:
- Summary metrics (tournaments played, avg points, avg rank, total points)
- Points by week line chart
- Full season log table

**Usage**:
```bash
# Edit season log
nano outputs/season_log.csv

# Or in Excel/Numbers
open outputs/season_log.csv
```

Add a new row after each tournament with your results.

---

### 4. ⚙️ Settings

**Purpose**: System status and configuration

**Shows**:

#### File Paths
- Project root
- Output directory
- Field files location
- Model directory

#### Model Information
Status of each trained model:
- Win Model
- Top-5 Model
- Top-10 Model
- Top-20 Model

Shows file size and last modified date.

#### Data Status
- Master training data records
- Year range (2020-2025)
- Number of players
- Number of tournaments

#### System Actions
- Clear output files (with confirmation)
- Links to documentation

---

## Dashboard vs Command Line

### When to Use Dashboard

✅ **Best for**:
- First-time predictions
- Exploring results
- Trying different parameters
- Visual analysis
- Quick player lookup
- Season tracking

### When to Use Command Line

✅ **Best for**:
- Automated workflows
- Batch processing
- Scripting/cron jobs
- Fastest execution
- Remote/headless servers

**Both methods use the same prediction engine**, so results are identical.

---

## Screenshots & Examples

### Running Predictions

1. Open dashboard → Go to "🎯 Run Predictions"
2. Fill in form:
   ```
   ESPN ID: 401811929
   Name: American Express
   Purse: 9600000
   Type: Standard
   ```
3. Click "Run Predictions"
4. Wait for completion (1-2 min)
5. View top 10 picks
6. Download CSV or picks report

### Viewing Results

1. Go to "📊 View Results"
2. Select tournament from dropdown
3. View summary stats
4. Explore tabs:
   - See top 20 picks
   - Filter full list
   - View charts
   - Search for specific players

### Analyzing Performance

1. Go to "📈 Analytics"
2. Create season log (first time)
3. After each tournament, update CSV:
   ```bash
   echo "2,2026-02-01,Farmers,Rahm,Clark,Day,T3,1st,T12,175,2/50,Clark won!" >> outputs/season_log.csv
   ```
4. Refresh dashboard to see updated stats

---

## Customization

### Change Port

Default port is 8501. To use different port:

```bash
streamlit run dashboard.py --server.port 8502
```

### Theme

Streamlit uses system theme by default. To customize, create `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"
```

### Add Custom Charts

Edit `dashboard.py` and add new visualization options in the "Charts" tab:

```python
elif chart_type == "Your Custom Chart":
    fig = px.scatter(...)  # Your Plotly chart
    st.plotly_chart(fig, use_container_width=True)
```

---

## Troubleshooting

### Dashboard won't start

**Error**: `ModuleNotFoundError: No module named 'streamlit'`

**Fix**:
```bash
pip3 install streamlit plotly
```

---

### Port already in use

**Error**: `Address already in use`

**Fix**: Use different port:
```bash
streamlit run dashboard.py --server.port 8502
```

Or kill existing process:
```bash
lsof -ti:8501 | xargs kill -9
```

---

### Predictions fail in dashboard

**Check**:
1. ESPN ID is correct
2. Tournament name doesn't have special characters
3. Check terminal output for detailed error
4. Try running command line version first:
   ```bash
   ./scripts/predictions/weekly_predictions.sh --espn-id 401811929 --name "American Express" --purse 9600000
   ```

---

### Charts not displaying

**Fix**: Install Plotly:
```bash
pip3 install plotly
```

---

## Advanced Features

### Run on Different Machine

Dashboard can run on a server and be accessed from any device:

```bash
# On server
streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8501

# Access from browser
http://[server-ip]:8501
```

### Password Protection

Add authentication:

```bash
streamlit run dashboard.py --server.headless true --server.fileWatcherType none --server.enableCORS false --server.enableXsrfProtection true
```

Then create `.streamlit/secrets.toml`:
```toml
password = "your_password_here"
```

Update `dashboard.py` to check password on load.

---

## Tips & Tricks

### Keyboard Shortcuts
- `Ctrl+R` / `Cmd+R` - Refresh dashboard
- `Ctrl+C` (in terminal) - Stop dashboard

### Best Practices

1. **Before predictions**: Verify ESP N ID is correct
2. **After predictions**: Download CSV backup
3. **Weekly routine**:
   - Wednesday: Run predictions
   - Thursday: Review on dashboard
   - Sunday: Update season log

### Performance

Dashboard uses same prediction engine as CLI:
- **Speed**: ~1-2 minutes per prediction
- **Accuracy**: Identical to command line
- **Resources**: ~100MB RAM

---

## Future Enhancements

Planned features:
- 📊 Model performance metrics
- 📈 Prediction accuracy tracking
- 🔄 Auto-refresh after tournament ends
- 📤 Export picks to different formats
- 🎯 Optimal lineup generator
- 📧 Email picks to yourself

See [docs/PIPELINE_ENHANCEMENTS.md](docs/PIPELINE_ENHANCEMENTS.md) for full roadmap.

---

## Files

**Dashboard files**:
- `dashboard.py` - Main dashboard application
- `launch_dashboard.sh` - Launch script
- `DASHBOARD_GUIDE.md` - This file

**Related**:
- `scripts/predictions/weekly_predictions.sh` - Backend prediction engine
- `outputs/season_log.csv` - Performance tracking data

---

## FAQ

**Q: Can I run predictions offline?**
A: Yes, but you need field data. The ESPN scraper requires internet.

**Q: How do I stop the dashboard?**
A: Press `Ctrl+C` in the terminal where it's running.

**Q: Can multiple people use the dashboard?**
A: Yes, but only one person can run predictions at a time (file locking).

**Q: Does the dashboard store my picks?**
A: Predictions are saved as CSV files in `outputs/`. Update season log manually.

**Q: Can I use this on Windows?**
A: Dashboard works on Windows, but you may need to adjust file paths in `dashboard.py`.

---

## Support

**Issues**:
- Check terminal output for errors
- Review [WEEKLY_WORKFLOW.md](WEEKLY_WORKFLOW.md)
- Try command line version first

**Improvements**:
- Edit `dashboard.py` directly
- Submit feature requests via GitHub issues

---

**Ready to use the dashboard! Launch it and start making predictions.** 🎯⛳

*Last updated: January 19, 2026*