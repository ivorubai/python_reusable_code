root@controlplane ~ ✖ cat /root/code/verify_environment.py
#!/usr/bin/env python3
"""
Environment Verification Script
Confirms your AI lab environment is properly configured.
"""

import os
import sys
import subprocess

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return version.major >= 3 and version.minor >= 8

def check_virtual_env():
    """Check if running in virtual environment"""
    print("\n🐍 Virtual Environment Check:")

    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print(f"  ✅ Virtual environment active: {sys.prefix}")
        return True
    else:
        print("  ❌ NOT running in virtual environment!")
        print("\n" + "="*60)
        print("⚠️  CRITICAL: You MUST activate the virtual environment!")
        print("⚠️  The OpenAI package is installed in /root/venv")
        print("⚠️  Without activation, ALL tasks will fail!")
        print("\n📌 Run this command NOW:")
        print("   source /root/venv/bin/activate")
        print("="*60)
        return False

def check_openai_package():
    """Check if OpenAI package is installed"""
    print("\n📦 Checking OpenAI Package:")

    try:
        result = subprocess.run(
            ["pip", "show", "openai"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    version = line.split(':')[1].strip()
                    print(f"  ✅ openai package installed (version {version})")
                    return True
        else:
            print("  ❌ OpenAI package NOT found")
            print("  📌 This means virtual environment is not activated!")
            return False
    except Exception as e:
        print(f"  ❌ Error checking package: {e}")
        return False

def check_api_config():
    """Verify API configuration"""
    print("\n🔑 Checking API Configuration:")

    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")

    all_good = True

    if api_key:
        print(f"  ✅ OPENAI_API_KEY is configured ({len(api_key)} chars)")
    else:
        print("  ❌ OPENAI_API_KEY not found")
        all_good = False

    if api_base:
        print(f"  ✅ OPENAI_API_BASE is configured: {api_base}")
    else:
        print("  ❌ OPENAI_API_BASE not found")
        all_good = False

    return all_good

def test_import():
    """Test if we can import OpenAI"""
    print("\n🔬 Testing OpenAI Import:")

    try:
        import openai
        print("  ✅ Successfully imported openai module")
        return True
    except ImportError:
        print("  ❌ Cannot import openai - virtual environment not activated!")
        return False

def main():
    """Run all environment checks"""
    print("="*60)
    print("🔧 AI Lab - Environment Setup & Verification")
    print("="*60)

    # CRITICAL: Check virtual environment first
    venv_active = check_virtual_env()

    if not venv_active:
        print("\n❌ STOPPING HERE - Activate virtual environment first!")
        print("   Then run this script again.")
        sys.exit(1)

    # If venv is active, continue with other checks
    checks = {
        "Python Version": check_python_version(),
        "OpenAI Package": check_openai_package(),
        "API Configuration": check_api_config(),
        "Import Test": test_import()
    }

    # Summary
    print("\n" + "="*60)
    print("📊 Environment Check Summary")
    print("="*60)

    all_passed = True
    for check, passed in checks.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {check}: {status}")
        if not passed:
            all_passed = False

    # Create marker file if all checks pass
    if all_passed:
        os.makedirs("/root/markers", exist_ok=True)
        with open("/root/markers/environment_verified.txt", "w") as f:
            f.write("ENVIRONMENT_VERIFIED")

        print("\n" + "="*60)
        print("🎉 Environment setup completed successfully!")
        print("✅ You're ready to start the AI tasks!")
        print("="*60)
        print("\n💡 Remember: Keep the virtual environment activated")
        print("   for all upcoming tasks!")
    else:
        print("\n" + "="*60)
        print("⚠️ Some checks failed. Please fix the issues above.")
        print("="*60)
        sys.exit(1)

if __name__ == "__main__":
    main()
