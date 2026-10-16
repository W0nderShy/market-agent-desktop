from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'scripts'))
from run_market_skill import main
raise SystemExit(main(['market-trend']))
