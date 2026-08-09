import getpass
import hashlib
import sys


def main():
    try:
        # Prompt securely for password without echoing to terminal
        password = getpass.getpass("Enter password to hash: ")
        confirm = getpass.getpass("Confirm password: ")
        
        if password != confirm:
            print("Error: Passwords do not match.", file=sys.stderr)
            sys.exit(1)
            
        # Generate SHA-256 hash
        hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()
        
        print("\nHashed Password (SHA-256):")
        print(hashed)
        
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled.")
        sys.exit(0)

if __name__ == "__main__":
    main()
