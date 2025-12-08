import os
import sys

print(f"Executable: {sys.executable}")
print(f"CWD: {os.getcwd()}")
print("Sys Path:")
for p in sys.path:
    print(f"  - {p}")

try:
    import langgraph
    print(f"Successfully imported langgraph: {langgraph.__file__}")
except ImportError as e:
    print(f"Failed to import langgraph: {e}")
