#!/bin/bash
# Launch Golf Prediction Dashboard
#
# Usage:
#   ./launch_dashboard.sh

cd /Users/jacklegnon/Desktop/golf_data

echo "========================================================================"
echo "  Launching Golf Prediction Dashboard"
echo "========================================================================"
echo ""
echo "The dashboard will open in your browser at:"
echo "  http://localhost:8501"
echo ""
echo "To stop the dashboard, press Ctrl+C"
echo ""
echo "========================================================================"
echo ""

# Launch Streamlit
streamlit run dashboard.py --server.headless true