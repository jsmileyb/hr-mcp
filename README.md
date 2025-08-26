# HR-MCP

A Python-based project for HR management using Model Context Protocol (MCP).

## Project Structure
- `main.py`: Main application entry point
- `utils/`: Utility modules
- `requirements.txt`: Python dependencies
- `Dockerfile` & `compose.yaml`: Containerization and orchestration

## Setup
1. **Clone the repository**
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the application**:
   ```bash
   python main.py
   ```

## Docker Usage
To build and run with Docker:
```bash
docker build -t hr-mcp .
docker run --rm -it hr-mcp
```

Or use Docker Compose:
```bash
docker compose up --build
```

## Configuration
Edit `utils/config.py` for custom settings.

## Contributing
Pull requests are welcome. For major changes, please open an issue first.

## License
MIT
