"""
Extract complete stress-strain data from dogbone tensile ODB.
Run inside Abaqus Python: abaqus python extract_stress_strain.py
"""
import json
import os
import sys

def extract_stress_strain(odb_path, output_path):
    """Extract S22 vs LE22 from all frames across all elements in the gauge section."""
    from odbAccess import openOdb
    
    odb = openOdb(path=odb_path, readOnly=True)
    
    try:
        step_names = list(odb.steps.keys())
        if not step_names:
            print("ERROR: No steps in ODB")
            return
        
        step = odb.steps[step_names[0]]
        print(f"Step: {step.name}")
        print(f"Frames: {len(step.frames)}")
        
        results = []
        
        for i, frame in enumerate(step.frames):
            frame_data = {
                "frame": i,
                "frameValue": frame.frameValue,
            }
            
            try:
                # Stress S22
                if "S" in frame.fieldOutputs:
                    s_fo = frame.fieldOutputs["S"]
                    s22 = s_fo.getSubset(componentLabel="S22")
                    s22_values = [v.data for v in s22.values]
                    if s22_values:
                        frame_data["avg_s22"] = sum(s22_values) / len(s22_values)
                        frame_data["max_s22"] = max(s22_values)
                        frame_data["min_s22"] = min(s22_values)
                    
                    # Mises
                    s_mises = s_fo.getSubset(componentLabel="Mises")
                    s_mises_values = [v.data for v in s_mises.values]
                    if s_mises_values:
                        frame_data["avg_mises"] = sum(s_mises_values) / len(s_mises_values)
                        frame_data["max_mises"] = max(s_mises_values)
                
                # Log strain LE22
                if "LE" in frame.fieldOutputs:
                    le_fo = frame.fieldOutputs["LE"]
                    le22 = le_fo.getSubset(componentLabel="LE22")
                    le22_values = [v.data for v in le22.values]
                    if le22_values:
                        frame_data["avg_le22"] = sum(le22_values) / len(le22_values)
                        frame_data["max_le22"] = max(le22_values)
                        frame_data["min_le22"] = min(le22_values)
                
                # PEEQ
                if "PEEQ" in frame.fieldOutputs:
                    peeq_fo = frame.fieldOutputs["PEEQ"]
                    peeq_values = [v.data for v in peeq_fo.values]
                    if peeq_values:
                        frame_data["avg_peeq"] = sum(peeq_values) / len(peeq_values)
                        frame_data["max_peeq"] = max(peeq_values)
                
                # Displacement U2
                if "U" in frame.fieldOutputs:
                    u_fo = frame.fieldOutputs["U"]
                    u2 = u_fo.getSubset(componentLabel="U2")
                    u2_values = [v.data for v in u2.values]
                    if u2_values:
                        frame_data["avg_u2"] = sum(u2_values) / len(u2_values)
                        frame_data["max_u2"] = max(u2_values)
                        frame_data["min_u2"] = min(u2_values)
                
            except Exception as e:
                frame_data["error"] = str(e)
            
            results.append(frame_data)
            print(f"  Frame {i}: frameValue={frame.frameValue:.4f}, "
                  f"avg_s22={frame_data.get('avg_s22', 'N/A')}, "
                  f"avg_le22={frame_data.get('avg_le22', 'N/A')}")
        
        # Write output
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\nData written to: {output_path}")
        print(f"Total frames: {len(results)}")
        
        # Also write a simple CSV for easy plotting
        csv_path = output_path.replace('.json', '.csv')
        with open(csv_path, 'w') as f:
            # Header
            headers = ["frame", "frameValue", "avg_s22", "max_s22", "avg_mises", "max_mises", 
                       "avg_le22", "max_le22", "avg_peeq", "max_peeq", "avg_u2", "max_u2"]
            f.write(",".join(headers) + "\n")
            for r in results:
                row = [str(r.get(h, "")) for h in headers]
                f.write(",".join(row) + "\n")
        print(f"CSV written to: {csv_path}")
        
    finally:
        odb.close()


if __name__ == "__main__":
    odb_path = r"R:\100_Private\WQG\codex\ABAQUS MCP\abaqus-mcp-pro\examples\output\dogbone_tensile\dogbone_tensile.odb"
    output_path = r"R:\100_Private\WQG\codex\ABAQUS MCP\abaqus-mcp-pro\examples\output\dogbone_tensile\stress_strain_data.json"
    
    extract_stress_strain(odb_path, output_path)
