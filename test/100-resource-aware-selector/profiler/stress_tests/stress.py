import os
import time
import platform
import numpy as np
import psutil
from multiprocessing import Pool, cpu_count

# Stress Settings
DURATION = 60  # seconds to stress
MEMORY_SIZE_MB = 1024  # memory to allocate per process
FILE_SIZE_MB = 500  # disk I/O per process

# ──────────────────────── STRESS FUNCTIONS ──────────────────────── #
def cpu_stress():
    start = time.time()
    while time.time() - start < DURATION:
        x = 999999
        for _ in range(10_000_000):
            x = (x ** 0.5) ** 2

def memory_stress():
    size = MEMORY_SIZE_MB * 1024 * 1024 // 8  # 8 bytes per float64
    arr = np.ones(size, dtype=np.float64)
    start = time.time()
    while time.time() - start < DURATION:
        arr *= 1.0000001

def disk_stress():
    filename = f'stressfile_{os.getpid()}.bin'
    data = os.urandom(1024 * 1024)  # 1MB
    with open(filename, 'wb') as f:
        for _ in range(FILE_SIZE_MB):
            f.write(data)
    with open(filename, 'rb') as f:
        while f.read(1024 * 1024):
            pass
    os.remove(filename)

def full_stress():
    cpu_stress()
    memory_stress()
    disk_stress()

def run_full_stress(_):
    full_stress()

# ──────────────────────── SYSTEM INFO ──────────────────────── #
def print_system_info():
    print("🧩 System Information")
    print(f"🖥  OS: {platform.system()} {platform.release()}")
    print(f"💻  CPU: {platform.processor() or 'Unknown'}")
    print(f"🔢  Cores: {cpu_count()} physical/logical")
    print(f"🧠  Total RAM: {psutil.virtual_memory().total / 1024**3:.2f} GB")
    print(f"📉  Available RAM: {psutil.virtual_memory().available / 1024**3:.2f} GB")
    print("-" * 50)

def print_memory_stats():
    vm = psutil.virtual_memory()
    print(f"🧠  RAM: Used {vm.used / 1024**3:.2f} GB / {vm.total / 1024**3:.2f} GB")
    print(f"📉  Available: {vm.available / 1024**3:.2f} GB")
    print("-" * 50)

# ──────────────────────── MAIN FUNCTION ──────────────────────── #
def stress_launcher():
    print("⚙️  Preparing to stress your machine...\n")
    print_system_info()

    print(f"🔥 Stressing all {cpu_count()} CPU cores for {DURATION} seconds...")
    print(f"🧠 Each core will use ~{MEMORY_SIZE_MB}MB RAM")
    print(f"💾 Each core will write/read ~{FILE_SIZE_MB}MB of disk\n")
    print_memory_stats()

    start_time = time.time()

    with Pool(cpu_count()) as pool:
        pool.map(run_full_stress, range(cpu_count()))

    end_time = time.time()
    duration = end_time - start_time

    print("✅ Stress test completed!")
    print(f"🕒 Total duration: {duration:.2f} seconds\n")
    print("📊 Post-stress memory stats:")
    print_memory_stats()

if __name__ == '__main__':
    stress_launcher()
