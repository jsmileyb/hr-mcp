import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import get_graph_token

def main():
    token = get_graph_token()
    if token:
        print(f"Access token: {token}")
    else:
        print("Failed to obtain token.")

if __name__ == "__main__":
    main()
