import os
import time
import platform
import threading
import logging
import subprocess
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import numpy as np
import psutil

# Enhanced Configuration
CONFIG = {
    'DURATION': 120,  # seconds to stress
    'MEMORY_SIZE_MB': 2048,  # memory to allocate per process
    'FILE_SIZE_MB': 1000,  # disk I/O per process
    'LOG_INTERVAL': 2,  # seconds between logs
    'TEMP_CHECK_INTERVAL': 5,  # seconds between temperature checks
    'GPU_MEMORY_STRESS_MB': 512,  # GPU memory to allocate if available
    'BENCHMARK_ITERATIONS': 1000000,  # CPU benchmark iterations
}

# Global variables for monitoring
monitoring_active = False
stress_results = {
    'start_time': None,
    'end_time': None,
    'peak_cpu_usage': 0,
    'peak_memory_usage': 0,
    'peak_temperature': 0,
    'gpu_info': None,
    'performance_scores': {},
    'system_info': {},
    'logs': []
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'stress_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ──────────────────────── GPU DETECTION & STRESS ──────────────────────── #
def detect_gpu():
    """Detect available GPUs"""
    gpu_info = {'has_gpu': False, 'gpus': []}
    
    try:
        # Try NVIDIA GPUs first
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,temperature.gpu', 
                               '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split(', ')
                    if len(parts) >= 3:
                        gpu_info['gpus'].append({
                            'type': 'NVIDIA',
                            'name': parts[0].strip(),
                            'memory_mb': int(parts[1]) if parts[1].isdigit() else 0,
                            'temperature': int(parts[2]) if parts[2].isdigit() else 0
                        })
                        gpu_info['has_gpu'] = True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    
    # Try AMD GPUs
    try:
        result = subprocess.run(['rocm-smi', '--showtemp', '--showmeminfo'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and 'GPU' in result.stdout:
            gpu_info['gpus'].append({
                'type': 'AMD',
                'name': 'AMD GPU Detected',
                'memory_mb': 'Unknown',
                'temperature': 'Unknown'
            })
            gpu_info['has_gpu'] = True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    
    # Try Intel GPUs
    try:
        result = subprocess.run(['intel_gpu_top', '-l', '1'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            gpu_info['gpus'].append({
                'type': 'Intel',
                'name': 'Intel GPU Detected',
                'memory_mb': 'Unknown',
                'temperature': 'Unknown'
            })
            gpu_info['has_gpu'] = True
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    
    return gpu_info

def gpu_stress_nvidia():
    """Stress NVIDIA GPU using matrix operations"""
    try:
        import cupy as cp
        size = int(np.sqrt(CONFIG['GPU_MEMORY_STRESS_MB'] * 1024 * 1024 / 8))
        
        # Create large matrices on GPU
        a = cp.random.rand(size, size, dtype=cp.float32)
        b = cp.random.rand(size, size, dtype=cp.float32)
        
        start_time = time.time()
        while time.time() - start_time < CONFIG['DURATION']:
            # Intensive GPU operations
            c = cp.matmul(a, b)
            a = cp.sqrt(cp.abs(c))
            b = cp.sin(a) + cp.cos(a)
            cp.cuda.Stream.null.synchronize()
            
    except ImportError:
        logger.warning("CuPy not available for NVIDIA GPU stress test")
    except Exception as e:
        logger.error(f"GPU stress test failed: {e}")

def gpu_stress_cpu_fallback():
    """CPU-based GPU stress simulation"""
    size = min(1000, int(np.sqrt(CONFIG['GPU_MEMORY_STRESS_MB'] * 1024 / 8)))
    a = np.random.rand(size, size).astype(np.float32)
    b = np.random.rand(size, size).astype(np.float32)
    
    start_time = time.time()
    while time.time() - start_time < CONFIG['DURATION']:
        c = np.matmul(a, b)
        a = np.sqrt(np.abs(c))
        b = np.sin(a) + np.cos(a)

# ──────────────────────── ENHANCED STRESS FUNCTIONS ──────────────────────── #
def intense_cpu_stress(worker_id):
    """More intensive CPU stress with multiple algorithms"""
    logger.info(f"CPU Worker {worker_id} starting intensive stress test")
    
    start_time = time.time()
    operations_count = 0
    
    while time.time() - start_time < CONFIG['DURATION']:
        # Prime number generation
        for n in range(2, 1000):
            is_prime = True
            for i in range(2, int(n**0.5) + 1):
                if n % i == 0:
                    is_prime = False
                    break
        
        # Matrix operations
        size = 100
        a = np.random.rand(size, size)
        b = np.random.rand(size, size)
        c = np.matmul(a, b)
        eigenvals = np.linalg.eigvals(c)
        
        # Trigonometric calculations
        for i in range(10000):
            result = np.sin(i) * np.cos(i) + np.tan(i/100)
        
        # Floating point intensive operations
        x = 1.23456789
        for i in range(100000):
            x = (x ** 1.1) / 1.05
            if x > 1000000:
                x = 1.23456789
        
        operations_count += 1
    
    logger.info(f"CPU Worker {worker_id} completed {operations_count} operation cycles")
    return operations_count

def intense_memory_stress(worker_id):
    """Enhanced memory stress with various patterns"""
    logger.info(f"Memory Worker {worker_id} starting intensive memory stress")
    
    arrays = []
    start_time = time.time()
    
    try:
        # Allocate multiple arrays with different patterns
        for i in range(5):
            size = CONFIG['MEMORY_SIZE_MB'] * 1024 * 1024 // (8 * 5)
            arr = np.random.rand(size).astype(np.float64)
            arrays.append(arr)
        
        operation_count = 0
        while time.time() - start_time < CONFIG['DURATION']:
            for arr in arrays:
                # Memory intensive operations
                arr += np.random.rand(len(arr))
                arr = np.sort(arr)
                arr = np.fft.fft(arr[:min(1024, len(arr))])
                arr = np.real(arr)
                
                # Random access patterns
                indices = np.random.randint(0, len(arr), 10000)
                arr[indices] *= 1.001
                
            operation_count += 1
        
        logger.info(f"Memory Worker {worker_id} completed {operation_count} memory cycles")
        return operation_count
        
    except MemoryError:
        logger.warning(f"Memory Worker {worker_id} hit memory limit")
        return 0

def intense_disk_stress(worker_id):
    """Enhanced disk I/O stress with various patterns"""
    logger.info(f"Disk Worker {worker_id} starting intensive disk stress")
    
    filename = f'stress_disk_{worker_id}_{os.getpid()}.bin'
    operations_count = 0
    bytes_written = 0
    bytes_read = 0
    
    try:
        start_time = time.time()
        
        while time.time() - start_time < CONFIG['DURATION']:
            # Sequential write
            with open(filename, 'wb') as f:
                for chunk in range(CONFIG['FILE_SIZE_MB']):
                    data = os.urandom(1024 * 1024)  # 1MB random data
                    f.write(data)
                    bytes_written += len(data)
                    f.flush()
                    os.fsync(f.fileno())
            
            # Random access read
            with open(filename, 'rb') as f:
                file_size = os.path.getsize(filename)
                for _ in range(100):
                    pos = np.random.randint(0, max(1, file_size - 1024))
                    f.seek(pos)
                    data = f.read(1024)
                    bytes_read += len(data)
            
            # Append operations
            with open(filename, 'ab') as f:
                for _ in range(10):
                    data = os.urandom(10240)  # 10KB
                    f.write(data)
                    bytes_written += len(data)
                    f.flush()
            
            operations_count += 1
        
        os.remove(filename)
        logger.info(f"Disk Worker {worker_id} completed {operations_count} I/O cycles")
        logger.info(f"Disk Worker {worker_id} wrote {bytes_written/1024/1024:.2f}MB, read {bytes_read/1024/1024:.2f}MB")
        return operations_count
        
    except Exception as e:
        logger.error(f"Disk Worker {worker_id} error: {e}")
        if os.path.exists(filename):
            os.remove(filename)
        return 0

# ──────────────────────── MONITORING FUNCTIONS ──────────────────────── #
def get_cpu_temperature():
    """Get CPU temperature from various sources"""
    temp = None
    
    try:
        # Try psutil sensors (Linux/macOS)
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    for entry in entries:
                        if 'cpu' in name.lower() or 'core' in name.lower():
                            if temp is None or entry.current > temp:
                                temp = entry.current
                            break
    except:
        pass
    
    # Windows specific
    if temp is None and platform.system() == "Windows":
        try:
            import wmi
            w = wmi.WMI(namespace="root\\wmi")
            temperature_info = w.MSAcpi_ThermalZoneTemperature()
            if temperature_info:
                temp = (int(temperature_info[0].CurrentTemperature) / 10.0) - 273.15
        except:
            pass
    
    return temp

def get_gpu_temperature():
    """Get GPU temperature"""
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu', 
                               '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            temps = [int(x.strip()) for x in result.stdout.strip().split('\n') if x.strip().isdigit()]
            return max(temps) if temps else None
    except:
        pass
    return None

def system_monitor():
    """Continuous system monitoring during stress test"""
    global monitoring_active, stress_results
    
    logger.info("System monitoring started")
    
    while monitoring_active:
        try:
            # CPU and Memory stats
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # Temperature monitoring
            cpu_temp = get_cpu_temperature()
            gpu_temp = get_gpu_temperature()
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            
            # Network I/O
            net_io = psutil.net_io_counters()
            
            # Update peak values
            stress_results['peak_cpu_usage'] = max(stress_results['peak_cpu_usage'], cpu_percent)
            stress_results['peak_memory_usage'] = max(stress_results['peak_memory_usage'], memory.percent)
            
            if cpu_temp:
                stress_results['peak_temperature'] = max(stress_results['peak_temperature'], cpu_temp)
            
            # Log current stats
            log_entry = {
                'timestamp': human_readable_timestamp(datetime.now()),
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_gb': memory.used / 1024**3,
                'cpu_temp': cpu_temp,
                'gpu_temp': gpu_temp,
                'disk_read_mb': disk_io.read_bytes / 1024**2 if disk_io else None,
                'disk_write_mb': disk_io.write_bytes / 1024**2 if disk_io else None,
                'network_sent_mb': net_io.bytes_sent / 1024**2 if net_io else None,
                'network_recv_mb': net_io.bytes_recv / 1024**2 if net_io else None,
            }
            
            stress_results['logs'].append(log_entry)
            
            # Console output
            temp_str = f"{cpu_temp:.1f}°C" if cpu_temp else "N/A"
            gpu_temp_str = f"{gpu_temp:.1f}°C" if gpu_temp else "N/A"
            
            print(f"\r🔥 CPU: {cpu_percent:5.1f}% | 🧠 RAM: {memory.percent:5.1f}% | 🌡️ CPU: {temp_str} | 🎮 GPU: {gpu_temp_str}", end="", flush=True)
            
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
        
        time.sleep(CONFIG['LOG_INTERVAL'])

# ──────────────────────── BENCHMARK FUNCTIONS ──────────────────────── #
def cpu_benchmark():
    """CPU performance benchmark"""
    logger.info("Running CPU benchmark...")
    
    start_time = time.time()
    
    # Prime number calculation benchmark
    primes = []
    for n in range(2, 10000):
        is_prime = True
        for i in range(2, int(n**0.5) + 1):
            if n % i == 0:
                is_prime = False
                break
        if is_prime:
            primes.append(n)
    
    prime_time = time.time() - start_time
    
    # Matrix operations benchmark
    start_time = time.time()
    size = 500
    a = np.random.rand(size, size)
    b = np.random.rand(size, size)
    c = np.matmul(a, b)
    eigenvals = np.linalg.eigvals(c)
    matrix_time = time.time() - start_time
    
    # Floating point benchmark
    start_time = time.time()
    result = 0.0
    for i in range(1000000):
        result += np.sin(i) * np.cos(i) + np.sqrt(i)
    float_time = time.time() - start_time
    
    return {
        'prime_calculation_time': prime_time,
        'matrix_operations_time': matrix_time,
        'floating_point_time': float_time,
        'primes_found': len(primes),
        'total_score': 1000 / (prime_time + matrix_time + float_time)  # Higher is better
    }

def memory_benchmark():
    """Memory performance benchmark"""
    logger.info("Running memory benchmark...")
    
    # Sequential read/write
    size = 100 * 1024 * 1024  # 100MB
    
    start_time = time.time()
    arr = np.ones(size // 8, dtype=np.float64)
    write_time = time.time() - start_time
    
    start_time = time.time()
    total = np.sum(arr)
    read_time = time.time() - start_time
    
    # Random access
    start_time = time.time()
    indices = np.random.randint(0, len(arr), 100000)
    arr[indices] = np.random.rand(len(indices))
    random_time = time.time() - start_time
    
    return {
        'sequential_write_time': write_time,
        'sequential_read_time': read_time,
        'random_access_time': random_time,
        'memory_bandwidth_mb_s': (size / 1024**2) / (write_time + read_time),
        'total_score': 1000 / (write_time + read_time + random_time)
    }

def disk_benchmark():
    """Disk I/O performance benchmark"""
    logger.info("Running disk benchmark...")
    
    filename = f'benchmark_disk_{os.getpid()}.bin'
    file_size = 100 * 1024 * 1024  # 100MB
    
    try:
        # Sequential write
        start_time = time.time()
        with open(filename, 'wb') as f:
            data = os.urandom(1024 * 1024)  # 1MB chunks
            for _ in range(file_size // len(data)):
                f.write(data)
                f.flush()
        write_time = time.time() - start_time
        
        # Sequential read
        start_time = time.time()
        with open(filename, 'rb') as f:
            while f.read(1024 * 1024):
                pass
        read_time = time.time() - start_time
        
        # Random I/O
        start_time = time.time()
        with open(filename, 'r+b') as f:
            for _ in range(1000):
                pos = np.random.randint(0, file_size - 1024)
                f.seek(pos)
                f.read(1024)
        random_time = time.time() - start_time
        
        os.remove(filename)
        
        return {
            'sequential_write_mb_s': (file_size / 1024**2) / write_time,
            'sequential_read_mb_s': (file_size / 1024**2) / read_time,
            'random_io_time': random_time,
            'write_time': write_time,
            'read_time': read_time,
            'total_score': (file_size / 1024**2) / (write_time + read_time + random_time)
        }
        
    except Exception as e:
        logger.error(f"Disk benchmark failed: {e}")
        if os.path.exists(filename):
            os.remove(filename)
        return None

# ──────────────────────── SYSTEM INFO ──────────────────────── #
def get_detailed_system_info():
    """Get comprehensive system information"""
    info = {
        'timestamp': datetime.now().isoformat(),
        'platform': {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'architecture': platform.architecture(),
            'hostname': platform.node(),
        },
        'cpu': {
            'physical_cores': psutil.cpu_count(logical=False),
            'logical_cores': psutil.cpu_count(logical=True),
            'max_frequency': psutil.cpu_freq().max if psutil.cpu_freq() else None,
            'current_frequency': psutil.cpu_freq().current if psutil.cpu_freq() else None,
        },
        'memory': {
            'total_gb': psutil.virtual_memory().total / 1024**3,
            'available_gb': psutil.virtual_memory().available / 1024**3,
            'used_gb': psutil.virtual_memory().used / 1024**3,
            'percentage': psutil.virtual_memory().percent,
        },
        'disk': {},
        'network': {},
        'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat(),
    }
    
    # Disk information
    for partition in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            info['disk'][partition.device] = {
                'mountpoint': partition.mountpoint,
                'filesystem': partition.fstype,
                'total_gb': usage.total / 1024**3,
                'used_gb': usage.used / 1024**3,
                'free_gb': usage.free / 1024**3,
                'percentage': (usage.used / usage.total) * 100,
            }
        except PermissionError:
            continue
    
    # Network information
    net_info = psutil.net_if_addrs()
    for interface, addresses in net_info.items():
        info['network'][interface] = []
        for addr in addresses:
            info['network'][interface].append({
                'family': str(addr.family),
                'address': addr.address,
                'netmask': addr.netmask,
                'broadcast': addr.broadcast,
            })
    
    return info

def print_detailed_system_info():
    """Print comprehensive system information"""
    info = get_detailed_system_info()
    
    print("🔍 " + "="*60)
    print("🔍 COMPREHENSIVE SYSTEM ANALYSIS")
    print("🔍 " + "="*60)
    
    # Platform info
    print(f"🖥️  System: {info['platform']['system']} {info['platform']['release']}")
    print(f"🏗️  Architecture: {info['platform']['machine']} {info['platform']['architecture'][0]}")
    print(f"💻  Processor: {info['platform']['processor'] or 'Unknown'}")
    print(f"🏠  Hostname: {info['platform']['hostname']}")
    print(f"⏰  Boot Time: {human_readable_timestamp(info['boot_time'])}")
    
    # CPU info
    print(f"\n⚡ CPU INFORMATION")
    print(f"🔢  Physical Cores: {info['cpu']['physical_cores']}")
    print(f"🔢  Logical Cores: {info['cpu']['logical_cores']}")
    if info['cpu']['max_frequency']:
        print(f"📈  Max Frequency: {info['cpu']['max_frequency']:.2f} MHz")
        print(f"📊  Current Frequency: {info['cpu']['current_frequency']:.2f} MHz")
    
    # Memory info
    print(f"\n🧠 MEMORY INFORMATION")
    print(f"📊  Total RAM: {info['memory']['total_gb']:.2f} GB")
    print(f"💚  Available: {info['memory']['available_gb']:.2f} GB")
    print(f"🔴  Used: {info['memory']['used_gb']:.2f} GB ({info['memory']['percentage']:.1f}%)")
    
    # Disk info
    print(f"\n💾 DISK INFORMATION")
    for device, disk_info in info['disk'].items():
        print(f"📀  {device} ({disk_info['filesystem']})")
        print(f"    📁 Mount: {disk_info['mountpoint']}")
        print(f"    📊 Total: {disk_info['total_gb']:.2f} GB")
        print(f"    💚 Free: {disk_info['free_gb']:.2f} GB")
        print(f"    🔴 Used: {disk_info['used_gb']:.2f} GB ({disk_info['percentage']:.1f}%)")
    
    return info

# ──────────────────────── MAIN STRESS TEST ──────────────────────── #
def run_comprehensive_stress_test():
    """Run the complete stress test suite"""
    global monitoring_active, stress_results
    
    print("🚀 " + "="*60)
    print("🚀 ADVANCED SYSTEM STRESS TEST & BENCHMARK SUITE")
    print("🚀 " + "="*60)
    
    # Get system information
    stress_results['system_info'] = get_detailed_system_info()
    print_detailed_system_info()
    
    # Detect GPU
    gpu_info = detect_gpu()
    stress_results['gpu_info'] = gpu_info
    
    print(f"\n🎮 GPU DETECTION")
    if gpu_info['has_gpu']:
        for gpu in gpu_info['gpus']:
            print(f"✅  {gpu['type']} GPU: {gpu['name']}")
            if isinstance(gpu['memory_mb'], int):
                print(f"    💾 VRAM: {gpu['memory_mb']} MB")
            if isinstance(gpu['temperature'], int):
                print(f"    🌡️  Temperature: {gpu['temperature']}°C")
    else:
        print("❌  No supported GPU detected")
    
    # Configuration summary
    print(f"\n⚙️  STRESS TEST CONFIGURATION")
    print(f"⏱️  Duration: {CONFIG['DURATION']} seconds")
    print(f"🧠  Memory per process: {CONFIG['MEMORY_SIZE_MB']} MB")
    print(f"💾  Disk I/O per process: {CONFIG['FILE_SIZE_MB']} MB")
    print(f"📊  Monitoring interval: {CONFIG['LOG_INTERVAL']} seconds")
    
    # Run benchmarks first
    print(f"\n🏁 RUNNING PERFORMANCE BENCHMARKS...")
    stress_results['performance_scores']['cpu'] = cpu_benchmark()
    stress_results['performance_scores']['memory'] = memory_benchmark()
    stress_results['performance_scores']['disk'] = disk_benchmark()
    
    print(f"\n📊 BENCHMARK RESULTS:")
    print(f"⚡ CPU Score: {stress_results['performance_scores']['cpu']['total_score']:.2f}")
    print(f"🧠 Memory Score: {stress_results['performance_scores']['memory']['total_score']:.2f}")
    if stress_results['performance_scores']['disk']:
        print(f"💾 Disk Score: {stress_results['performance_scores']['disk']['total_score']:.2f}")
    
    # Start monitoring
    monitoring_active = True
    monitor_thread = threading.Thread(target=system_monitor, daemon=True)
    monitor_thread.start()
    
    print(f"\n🔥 STARTING INTENSIVE STRESS TEST...")
    print(f"🔥 This will stress ALL system components simultaneously!")
    print(f"🔥 Monitor your system temperature and stop if needed (Ctrl+C)")
    print(f"\n⏱️  Starting in 3 seconds...")
    time.sleep(3)
    
    stress_results['start_time'] = datetime.now().isoformat()
    
    try:
        # Create thread pools for different types of stress
        cpu_cores = psutil.cpu_count(logical=True)
        
        with ThreadPoolExecutor(max_workers=cpu_cores * 3) as executor:
            futures = []
            
            # CPU stress (one per logical core)
            for i in range(cpu_cores):
                futures.append(executor.submit(intense_cpu_stress, f"CPU-{i}"))
            
            # Memory stress (fewer processes to avoid memory exhaustion)
            memory_workers = max(1, cpu_cores // 2)
            for i in range(memory_workers):
                futures.append(executor.submit(intense_memory_stress, f"MEM-{i}"))
            
            # Disk stress (limited to avoid disk saturation)
            disk_workers = max(1, min(4, cpu_cores // 4))
            for i in range(disk_workers):
                futures.append(executor.submit(intense_disk_stress, f"DISK-{i}"))
            
            # GPU stress if available
            if gpu_info['has_gpu']:
                for i, gpu in enumerate(gpu_info['gpus']):
                    if gpu['type'] == 'NVIDIA':
                        futures.append(executor.submit(gpu_stress_nvidia))
                    else:
                        futures.append(executor.submit(gpu_stress_cpu_fallback))
            
            print(f"\n🚀 Launched {len(futures)} stress workers")
            print(f"🔥 CPU Workers: {cpu_cores}")
            print(f"🧠 Memory Workers: {memory_workers}")
            print(f"💾 Disk Workers: {disk_workers}")
            if gpu_info['has_gpu']:
                print(f"🎮 GPU Workers: {len(gpu_info['gpus'])}")
            
            # Wait for completion
            for future in futures:
                try:
                    result = future.result()
                    if result:
                        logger.info(f"Worker completed with result: {result}")
                except Exception as e:
                    logger.error(f"Worker failed: {e}")
    
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Stress test interrupted by user")
        logger.info("Stress test interrupted by user")
    
    finally:
        monitoring_active = False
        stress_results['end_time'] = datetime.now().isoformat()
        
        # Wait for monitor thread to finish
        if monitor_thread.is_alive():
            monitor_thread.join(timeout=5)
    
    # Generate final report
    generate_final_report()

def generate_final_report():
    """Generate comprehensive final report"""
    print(f"\n\n📋 " + "="*60)
    print(f"📋 STRESS TEST FINAL REPORT")
    print(f"📋 " + "="*60)
    
    if stress_results['start_time'] and stress_results['end_time']:
        start_dt = datetime.fromisoformat(stress_results['start_time'])
        end_dt = datetime.fromisoformat(stress_results['end_time'])
        duration = (end_dt - start_dt).total_seconds()
        
        print(f"⏱️  Test Duration: {human_readable_duration(duration)}")
        print(f"🕐  Start Time: {human_readable_timestamp(stress_results['start_time'])}")
        print(f"🕐  End Time: {human_readable_timestamp(stress_results['end_time'])}")
    
    # System performance during test
    print(f"\n📊 PEAK SYSTEM UTILIZATION")
    print(f"⚡ Peak CPU Usage: {stress_results['peak_cpu_usage']:.1f}%")
    print(f"🧠 Peak Memory Usage: {stress_results['peak_memory_usage']:.1f}%")
    if stress_results['peak_temperature'] > 0:
        print(f"🌡️  Peak Temperature: {stress_results['peak_temperature']:.1f}°C")
    
    # Benchmark scores
    print(f"\n🏆 PERFORMANCE BENCHMARK SCORES")
    if 'cpu' in stress_results['performance_scores']:
        cpu_score = stress_results['performance_scores']['cpu']
        print(f"⚡ CPU Performance Score: {cpu_score['total_score']:.2f}")
        print(f"   - Prime calculation: {cpu_score['prime_calculation_time']:.3f}s ({cpu_score['primes_found']} primes)")
        print(f"   - Matrix operations: {cpu_score['matrix_operations_time']:.3f}s")
        print(f"   - Floating point: {cpu_score['floating_point_time']:.3f}s")
    
    if 'memory' in stress_results['performance_scores']:
        mem_score = stress_results['performance_scores']['memory']
        print(f"🧠 Memory Performance Score: {mem_score['total_score']:.2f}")
        print(f"   - Memory bandwidth: {mem_score['memory_bandwidth_mb_s']:.2f} MB/s")
        print(f"   - Sequential write: {mem_score['sequential_write_time']:.3f}s")
        print(f"   - Sequential read: {mem_score['sequential_read_time']:.3f}s")
        print(f"   - Random access: {mem_score['random_access_time']:.3f}s")
    
    if 'disk' in stress_results['performance_scores'] and stress_results['performance_scores']['disk']:
        disk_score = stress_results['performance_scores']['disk']
        print(f"💾 Disk Performance Score: {disk_score['total_score']:.2f}")
        print(f"   - Sequential write: {disk_score['sequential_write_mb_s']:.2f} MB/s")
        print(f"   - Sequential read: {disk_score['sequential_read_mb_s']:.2f} MB/s")
        print(f"   - Random I/O time: {disk_score['random_io_time']:.3f}s")
    
    # GPU information
    if stress_results['gpu_info']['has_gpu']:
        print(f"\n🎮 GPU INFORMATION")
        for gpu in stress_results['gpu_info']['gpus']:
            print(f"✅ {gpu['type']}: {gpu['name']}")
    
    # System stability analysis
    print(f"\n🔍 SYSTEM STABILITY ANALYSIS")
    if len(stress_results['logs']) > 0:
        cpu_values = [log['cpu_percent'] for log in stress_results['logs'] if log['cpu_percent'] is not None]
        memory_values = [log['memory_percent'] for log in stress_results['logs'] if log['memory_percent'] is not None]
        temp_values = [log['cpu_temp'] for log in stress_results['logs'] if log['cpu_temp'] is not None]
        
        if cpu_values:
            print(f"⚡ CPU Usage - Avg: {np.mean(cpu_values):.1f}%, Max: {np.max(cpu_values):.1f}%, Min: {np.min(cpu_values):.1f}%")
        if memory_values:
            print(f"🧠 Memory Usage - Avg: {np.mean(memory_values):.1f}%, Max: {np.max(memory_values):.1f}%, Min: {np.min(memory_values):.1f}%")
        if temp_values:
            print(f"🌡️  Temperature - Avg: {np.mean(temp_values):.1f}°C, Max: {np.max(temp_values):.1f}°C, Min: {np.min(temp_values):.1f}°C")
        
        # Stability indicators
        if cpu_values:
            cpu_stability = np.std(cpu_values)
            print(f"📊 CPU Stability (lower is better): {cpu_stability:.2f}")
        
        if temp_values:
            temp_stability = np.std(temp_values)
            print(f"🌡️  Thermal Stability (lower is better): {temp_stability:.2f}")
    
    # Warnings and recommendations
    print(f"\n⚠️  WARNINGS & RECOMMENDATIONS")
    warnings = []
    
    if stress_results['peak_cpu_usage'] > 95:
        warnings.append("🔥 CPU usage exceeded 95% - consider better cooling")
    
    if stress_results['peak_memory_usage'] > 90:
        warnings.append("🧠 Memory usage exceeded 90% - consider more RAM")
    
    if stress_results['peak_temperature'] > 80:
        warnings.append(f"🌡️  CPU temperature reached {stress_results['peak_temperature']:.1f}°C - check cooling system")
    
    if not warnings:
        print("✅ No critical issues detected - system performed well under stress")
    else:
        for warning in warnings:
            print(warning)
    
    # Performance classification
    print(f"\n🏅 OVERALL SYSTEM PERFORMANCE RATING")
    total_score = 0
    score_count = 0
    
    if 'cpu' in stress_results['performance_scores']:
        total_score += stress_results['performance_scores']['cpu']['total_score']
        score_count += 1
    
    if 'memory' in stress_results['performance_scores']:
        total_score += stress_results['performance_scores']['memory']['total_score']
        score_count += 1
    
    if 'disk' in stress_results['performance_scores'] and stress_results['performance_scores']['disk']:
        total_score += stress_results['performance_scores']['disk']['total_score']
        score_count += 1
    
    if score_count > 0:
        avg_score = total_score / score_count
        
        if avg_score >= 100:
            rating = "🥇 EXCELLENT"
        elif avg_score >= 75:
            rating = "🥈 VERY GOOD"
        elif avg_score >= 50:
            rating = "🥉 GOOD"
        elif avg_score >= 25:
            rating = "⚡ FAIR"
        else:
            rating = "🐌 NEEDS IMPROVEMENT"
        
        print(f"🏆 Overall Score: {avg_score:.2f} - {rating}")
    
    # Save detailed report to file
    save_detailed_report()
    
    print(f"\n💾 Detailed logs saved to: stress_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    print(f"📊 JSON report saved to: stress_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    print(f"\n✅ STRESS TEST COMPLETED!")

def save_detailed_report():
    """Save detailed report to JSON file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'stress_test_report_{timestamp}.json'
    
    try:
        with open(filename, 'w') as f:
            json.dump(stress_results, f, indent=2, default=str)
        logger.info(f"Detailed report saved to {filename}")
    except Exception as e:
        logger.error(f"Failed to save detailed report: {e}")

def human_readable_duration(seconds):
    """Convert seconds to human-readable format (e.g., 1h 2m 3s)"""
    seconds = int(seconds)
    periods = [
        ('h', 3600),
        ('m', 60),
        ('s', 1)
    ]
    strings = []
    for suffix, length in periods:
        value = seconds // length
        if value > 0 or (suffix == 's' and not strings):
            strings.append(f"{value}{suffix}")
        seconds = seconds % length
    return ' '.join(strings)

def human_readable_timestamp(dt):
    """Convert datetime or ISO string to readable format"""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def main():
    """Main function to run the stress test"""
    try:
        print("🎯 Advanced System Stress Test & Benchmark Tool")
        print("⚠️  WARNING: This will stress your system intensively!")
        print("💡 Make sure your system has adequate cooling and power supply")
        print("🛑 Press Ctrl+C to stop the test at any time")
        
        response = input("\n🤔 Do you want to proceed? (y/N): ").lower().strip()
        
        if response in ['y', 'yes']:
            run_comprehensive_stress_test()
        else:
            print("❌ Stress test cancelled by user")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Program interrupted by user")
        logger.info("Program interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        logger.error(f"Fatal error: {e}")
    finally:
        # Cleanup
        monitoring_active = False
        print("\n🧹 Cleaning up...")

if __name__ == '__main__':
    main()