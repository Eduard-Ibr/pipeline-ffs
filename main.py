import math
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

def calculate_asme_b31g_modified(diameter, wall_thickness, defect_length, defect_depth, smys, smts, maop):
    """
    ASME B31G Modified Method Calculation
    """
    # 1. Calculate relative depth
    d_t = defect_depth / wall_thickness
    
    # 2. Calculate Z parameter
    z_val = (defect_length ** 2) / (diameter * wall_thickness)
    
    # 3. Calculate S_flow (Flow Stress)
    s_flow = 1.1 * smys
    if s_flow > smts:
        s_flow = smts
    
    # 4. Calculate Folias factor (M)
    if z_val <= 50:
        m_val = math.sqrt(1 + 0.6275 * z_val - 0.003375 * (z_val ** 2))
    else:
        m_val = 0.032 * z_val + 3.3
    
    # 5. Calculate failure stress
    stress_fail = s_flow * (1 - 0.85 * d_t) / (1 - 0.85 * d_t / m_val)
    
    # 6. Calculate failure pressure
    pressure_fail = 2 * stress_fail * wall_thickness / diameter
    
    # 7. Calculate Estimated Repair Factor (ERF)
    erf = maop / pressure_fail
    
    # Prepare results - no rounding for calculations, only for display
    results = {
        'd_t': d_t,
        'z_val': z_val,
        's_flow': s_flow,
        'm_val': m_val,
        'stress_fail': stress_fail,
        'pressure_fail': pressure_fail,
        'erf': erf,
        'repair_required': erf >= 1,
        'status': 'danger' if erf >= 1 else 'success'
    }
    
    return results

def calculate_remaining_life(diameter, wall_thickness, defect_length, defect_depth, smys, smts, maop, corrosion_rate):
    """
    Calculate remaining life and critical defect depth
    """
    # Store original depth
    original_depth = defect_depth
    
    # According to ASME B31G Modified, critical depth cannot be less than 20% of wall thickness
    min_critical_depth = 0.2 * wall_thickness
    
    # Find critical depth (when ERF = 1)
    critical_depth = max(defect_depth, min_critical_depth)
    max_iterations = 100
    tolerance = 0.001
    
    # Start from current depth or minimum critical depth, whichever is larger
    test_depth = max(defect_depth, min_critical_depth)
    
    for i in range(max_iterations):
        # Calculate ERF with current depth
        results = calculate_asme_b31g_modified(diameter, wall_thickness, defect_length, test_depth, smys, smts, maop)
        erf = results['erf']
        
        # Check if we're close enough to ERF = 1
        if abs(erf - 1.0) < tolerance:
            critical_depth = max(test_depth, min_critical_depth)  # Ensure minimum 20%
            break
        
        # Adjust depth
        if erf < 1.0:
            # Increase depth if ERF is still below 1
            test_depth += (wall_thickness - test_depth) * 0.1
        else:
            # Decrease depth if ERF is above 1
            test_depth -= test_depth * 0.1
        
        # Apply ASME B31G constraint: critical depth cannot be less than 20% of wall thickness
        test_depth = max(test_depth, min_critical_depth)
        
        # Safety check - don't exceed wall thickness
        if test_depth >= wall_thickness:
            critical_depth = wall_thickness
            break
            
    else:
        # If loop didn't break, use last value with constraint
        critical_depth = max(test_depth, min_critical_depth)
    
    # Calculate remaining life and corrosion tolerance
    if corrosion_rate > 0:
        depth_to_critical = critical_depth - original_depth
        if depth_to_critical > 0:
            remaining_life = depth_to_critical / corrosion_rate
            remaining_corrosion_tolerance = depth_to_critical
        else:
            remaining_life = 0
            remaining_corrosion_tolerance = 0
    else:
        remaining_life = float('inf')  # Infinite life if no corrosion
        remaining_corrosion_tolerance = critical_depth - original_depth
    
    return {
        'min_critical_depth': min_critical_depth,
        'remaining_life': remaining_life,
        'remaining_corrosion_tolerance': remaining_corrosion_tolerance,
        'corrosion_rate': corrosion_rate,
        'original_depth': original_depth,
        'wall_thickness': wall_thickness
    }

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    """API endpoint for calculation"""
    try:
        # Get data from form
        data = request.get_json()
        
        # Extract parameters
        diameter = float(data['diameter'])
        wall_thickness = float(data['wall_thickness'])
        defect_length = float(data['defect_length'])
        defect_depth = float(data['defect_depth'])
        smys = float(data['smys'])
        smts = float(data['smts'])
        maop = float(data['maop'])
        corrosion_rate = float(data.get('corrosion_rate', 0))
        
        # Validate data
        if (diameter <= 0 or wall_thickness <= 0 or defect_length <= 0 or 
            defect_depth <= 0 or smys <= 0 or smts <= 0 or maop <= 0):
            return jsonify({'error': 'All values must be positive'}), 400
        
        if defect_depth > wall_thickness:
            return jsonify({'error': 'Defect depth cannot exceed wall thickness'}), 400
        
        if corrosion_rate < 0:
            return jsonify({'error': 'Corrosion rate cannot be negative'}), 400
        
        # Perform calculation
        results = calculate_asme_b31g_modified(
            diameter, wall_thickness, defect_length, defect_depth, smys, smts, maop
        )
        
        # Calculate remaining life if corrosion rate provided
        if corrosion_rate > 0:
            life_results = calculate_remaining_life(
                diameter, wall_thickness, defect_length, defect_depth, smys, smts, maop, corrosion_rate
            )
            results.update(life_results)
        
        return jsonify(results)
        
    except ValueError:
        return jsonify({'error': 'Invalid data format. Please ensure all fields contain numbers'}), 400
    except Exception as e:
        return jsonify({'error': f'Calculation error: {str(e)}'}), 500

@app.route('/example')
def load_example():
    """Load test example"""
    example_data = {
        'diameter': 506,
        'wall_thickness': 6.35,
        'defect_length': 200,
        'defect_depth': 2.5,
        'smys': 360,
        'smts': 455,
        'maop': 1.5,
        'corrosion_rate': 0.1
    }
    return jsonify(example_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
