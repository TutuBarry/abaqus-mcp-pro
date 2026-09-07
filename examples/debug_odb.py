"""Debug ODB: print available fields and components."""
import json

odb_path = r"R:\100_Private\WQG\codex\ABAQUS MCP\abaqus-mcp-pro\examples\output\dogbone_tensile\dogbone_tensile.odb"

from odbAccess import openOdb

odb = openOdb(path=odb_path, readOnly=True)
try:
    step = odb.steps[list(odb.steps.keys())[0]]
    frame = step.frames[-1]
    print(f"Step: {step.name}")
    print(f"Last frame: {frame.frameId}, value={frame.frameValue}")
    print(f"\nAvailable field outputs:")
    for name in sorted(frame.fieldOutputs.keys()):
        fo = frame.fieldOutputs[name]
        print(f"  {name}: type={fo.type}")
        
        # Get component labels
        if hasattr(fo, 'componentLabels'):
            print(f"    componentLabels: {fo.componentLabels}")
        
        # Try different access methods
        try:
            vals = fo.values
            first_vals = [v.data for v in vals[:5]]
            print(f"    first 5 values (direct): {first_vals}")
        except Exception as e:
            print(f"    direct values error: {e}")
        
        # Try getSubset
        if hasattr(fo, 'componentLabels') and fo.componentLabels:
            for cl in fo.componentLabels[:3]:
                try:
                    sub = fo.getSubset(componentLabel=cl)
                    sub_vals = [v.data for v in sub.values[:3]]
                    print(f"    {cl} first 3: {sub_vals}")
                except Exception as e:
                    print(f"    {cl} error: {e}")
        print()
finally:
    odb.close()
