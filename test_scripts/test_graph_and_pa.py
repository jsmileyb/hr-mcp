import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import get_graph_token, call_pa_workflow

def main():
    email = "smiley.baltz@greshamsmith.com"
    print(f"Testing get_graph_token()...")
    token = get_graph_token()
    print(f"Token: {token}")
    if not token:
        print("Failed to obtain token. Aborting workflow call.")
        return
    print(f"Testing call_pa_workflow() with email: {email}")
    response = call_pa_workflow(email)
    print(f"Workflow response: {response}")

if __name__ == "__main__":
    main()
