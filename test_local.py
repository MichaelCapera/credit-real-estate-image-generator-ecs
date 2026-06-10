import os
import sys

# --- SIMULATE ECS ENVIRONMENT VARIABLES ---
# Configure the production AWS API Gateway endpoint data feed URL
os.environ['API_URL'] = "https://8xuawsbnzg.execute-api.us-east-1.amazonaws.com/dev/data-properties"
os.environ['IMAGES_QUANTITY'] = "3"
os.environ['DEBUG_MODE'] = "False"

# Temporary mock credentials to pass app.py initialization validation checks locally
os.environ['GMAIL_USER'] = "creditofincaraiz@gmail.com"
os.environ['GMAIL_APP_PASSWORD'] = "vikj brys lqcs ezti"
os.environ['RECIPIENT_EMAILS'] = "michaelcapera@gmail.com"

# Force project root path mapping to prevent 'ModuleNotFoundError: No module named "src"'
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

try:
    # Import the main execution orchestrator directly from the src package
    from src.app import main
except ImportError as e:
    print(f"❌ Critical Import Error: Could not locate 'src/app.py'.")
    print(f"Error details: {e}")
    sys.exit(1)

if __name__ == "__main__":
    print("\n🚀 --- STARTING LOCAL ECS CONTAINER SIMULATION ---")
    print(f"Environment API_URL configured to: {os.getenv('API_URL')}")
    print(f"Images quantity to process: {os.getenv('IMAGES_QUANTITY')}\n")
    
    # Trigger the core application engine process
    main()
    
    print("\n🏁 --- CONTAINER SIMULATION FINISHED ---")