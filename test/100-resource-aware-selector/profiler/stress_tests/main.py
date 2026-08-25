import subprocess
import sys
import os

BENCHMARKS = [
    ("CPU Intensive Benchmark", "CPU-Intensive_Benchmark.py"),
    ("Disk I/O Benchmark", "Diskio.py"),
    ("Memory Bandwidth Benchmark", "mbb.py"),
    ("Multicore CPU Stress Test", "Multicore_CPU_Stress_Test.py"),
    ("Multicore Parallel Sort", "multicore.py"),
    ("Quicksort Single Core", "quicksort_single_core.py"),
    ("Full System Stress Test", "stress.py"),
    ("Advanced Stress Test (stress2)", "stress2.py"),
]

def print_menu():
    print("\nSystem Benchmark & Stress Test Suite")
    print("Select a benchmark or stress test to run:")
    for idx, (desc, _) in enumerate(BENCHMARKS, 1):
        print(f"  {idx}. {desc}")
    print("  0. Exit")

def run_script(script):
    if script.endswith('.py'):
        cmd = [sys.executable, script]
    else:
        cmd = [script]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running {script}: {e}")

def main():
    while True:
        print_menu()
        try:
            choice = int(input("Enter your choice: "))
        except ValueError:
            print("Invalid input. Please enter a number.")
            continue
        if choice == 0:
            print("Exiting.")
            break
        elif 1 <= choice <= len(BENCHMARKS):
            script = BENCHMARKS[choice - 1][1]
            if not os.path.exists(script):
                print(f"Script {script} not found.")
                continue
            print(f"\nRunning {BENCHMARKS[choice - 1][0]}...\n")
            run_script(script)
            print("\n--- Test finished ---\n")
        else:
            print("Invalid choice. Try again.")

if __name__ == "__main__":
    main()
