"""Abaqus Python entrypoint for reproducible KPI extraction."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from abaqus_mcp_pro.kpi_runtime import query_odb


def main():
    from odbAccess import openOdb
    config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    odb = openOdb(path=config['odb_path'], readOnly=True)
    try:
        results = query_odb(odb, config['queries'])
    finally:
        odb.close()
    Path(config['result_path']).write_text(json.dumps({
        'results': results, 'error_count': sum(bool(r['error']) for r in results)
    }, allow_nan=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
