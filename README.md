Streamlit app is now running on port 8501. Access it at: http://localhost:8501

The command used:
```bash
lsof -ti:8501 | xargs kill -9 2>/dev/null; streamlit run dashboard/app.py --server.port 8501 &
```

This kills any existing process on port 8501, then starts the Streamlit dashboard in the background. Navigate to the **🔬 Historical Trainer** page to run a new training session with the improved strategy.