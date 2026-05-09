import os


def test_frontend_files_exist():
    """Test that required frontend files exist"""
    frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'frontend')
    assert os.path.exists(os.path.join(frontend_dir, 'index.html'))
    assert os.path.exists(os.path.join(frontend_dir, 'main.ts'))
    assert os.path.exists(os.path.join(frontend_dir, 'style.css'))

def test_backend_files_exist():
    """Test that required backend files exist"""
    backend_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'backend')
    assert os.path.exists(os.path.join(backend_dir, 'main.py'))
    assert os.path.exists(os.path.join(backend_dir, 'engine_bridge.py'))

def test_config_files_exist():
    """Test that configuration files exist"""
    base_dir = os.path.join(os.path.dirname(__file__), '..')
    assert os.path.exists(os.path.join(base_dir, 'requirements.txt'))
    assert os.path.exists(os.path.join(base_dir, 'package.json'))
    assert os.path.exists(os.path.join(base_dir, 'tsconfig.json'))
    assert os.path.exists(os.path.join(base_dir, 'vite.config.ts'))
