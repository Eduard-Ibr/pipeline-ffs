import math
import os
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

def calculate_asme_b31g_modified(diameter, wall_thickness, defect_length, defect_depth, smys, smts, maop):
    """
    ASME B31G Modified Method Calculation
    """
    # Calculate relative depth
    d_t = defect_depth / wall_thickness
    
    # Calculate Z parameter
    z_val = (defect_length ** 2) / (diameter * wall_thickness)
    
    # Calculate Flow Stress
    s_flow = min(1.1 * smys, smts)
    
    # Calculate Folias factor
    if z_val <= 50:
        m_val = math.sqrt(1 + 0.6275 * z_val - 0.003375 * z_val ** 2)
    else:
        m_val = 0.032 * z_val + 3.3
    
    # Calculate failure stress and pressure
    stress_fail = s_flow * (1 - 0.85 * d_t) / (1 - 0.85 * d_t / m_val)
    pressure_fail = 2 * stress_fail * wall_thickness / diameter
    erf = maop / pressure_fail
    
    return {
        'd_t': round(d_t, 4),
        'z_val': round(z_val, 4),
        's_flow': round(s_flow, 2),
        'm_val': round(m_val, 4),
        'stress_fail': round(stress_fail, 2),
        'pressure_fail': round(pressure_fail, 3),
        'erf': round(erf, 3),
        'repair_required': erf >= 1,
        'method': 'ASME B31G Modified'
    }

def calculate_dnv_rp_f101(diameter, wall_thickness, defect_length, defect_depth, smts, maop, safety_class='medium'):
    """
    DNV RP F101 Calculation for corroded pipelines
    """
    # Relative depth
    d_t = defect_depth / wall_thickness
    
    # Folias factor parameter
    lambda_val = defect_length / math.sqrt(diameter * wall_thickness)
    
    # Folias factor calculation
    if lambda_val <= math.sqrt(20):
        m_val = math.sqrt(1 + 0.6275 * lambda_val**2 - 0.003375 * lambda_val**4)
    else:
        m_val = 0.032 * lambda_val**2 + 3.3
    
    # Safety factors
    safety_factors = {
        'low': {'gamma_m': 1.15, 'gamma_d': 1.0},
        'medium': {'gamma_m': 1.15, 'gamma_d': 1.05},
        'high': {'gamma_m': 1.15, 'gamma_d': 1.15}
    }
    
    gamma_m = safety_factors[safety_class]['gamma_m']
    gamma_d = safety_factors[safety_class]['gamma_d']
    
    # Calculate failure pressure (pressure resistance)
    p_fail = (2 * wall_thickness * smts / (diameter * gamma_m * gamma_d)) * ((1 - d_t) / (1 - d_t / m_val))
    
    # Calculate utilization factor but call it ERF for consistency
    utilization = maop / p_fail
    
    return {
        'd_t': round(d_t, 4),
        'lambda_val': round(lambda_val, 4),
        'm_val': round(m_val, 4),
        'gamma_m': round(gamma_m, 3),
        'gamma_d': round(gamma_d, 3),
        'pressure_fail': round(p_fail, 3),
        'erf': round(utilization, 3),  # Using utilization but calling it ERF
        'repair_required': utilization >= 1,
        'method': 'DNV RP F101',
        'safety_class': safety_class
    }

def calculate_remaining_life(diameter, wall_thickness, defect_length, defect_depth, smys, smts, maop, corrosion_rate, method='asme'):
    """
    Calculate remaining life and critical defect depth
    """
    original_depth = defect_depth
    min_critical_depth = 0.2 * wall_thickness
    
    # Find critical depth using binary search
    low, high = max(defect_depth, min_critical_depth), wall_thickness
    critical_depth = high
    
    for _ in range(50):  # 50 iterations for precision
        mid = (low + high) / 2
        
        if method == 'asme':
            results = calculate_asme_b31g_modified(diameter, wall_thickness, defect_length, mid, smys, smts, maop)
            factor = results['erf']
        else:
            results = calculate_dnv_rp_f101(diameter, wall_thickness, defect_length, mid, smts, maop)
            factor = results['erf']
        
        if abs(factor - 1.0) < 0.001:
            critical_depth = mid
            break
        elif factor < 1.0:
            low = mid
        else:
            high = mid
    
    critical_depth = max(critical_depth, min_critical_depth)
    
    # Calculate remaining life
    if corrosion_rate > 0:
        depth_to_critical = critical_depth - original_depth
        if depth_to_critical > 0:
            remaining_life = depth_to_critical / corrosion_rate
            remaining_corrosion_tolerance = depth_to_critical
        else:
            remaining_life = 0
            remaining_corrosion_tolerance = 0
    else:
        remaining_life = float('inf')
        remaining_corrosion_tolerance = critical_depth - original_depth
    
    return {
        'min_critical_depth': round(min_critical_depth, 3),
        'remaining_life': round(remaining_life, 2) if remaining_life != float('inf') else 'Infinite',
        'remaining_corrosion_tolerance': round(remaining_corrosion_tolerance, 3),
        'corrosion_rate': round(corrosion_rate, 3),
        'original_depth': round(original_depth, 3),
        'wall_thickness': round(wall_thickness, 3)
    }

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    """API endpoint for calculation"""
    try:
        data = request.get_json()
        
        # Extract and validate parameters
        required_params = ['diameter', 'wall_thickness', 'defect_length', 'defect_depth', 'smys', 'smts', 'maop']
        params = {}
        
        for param in required_params:
            value = float(data[param])
            if value <= 0:
                return jsonify({'error': f'{param.replace("_", " ").title()} must be positive'}), 400
            params[param] = value
        
        # Optional parameters
        corrosion_rate = float(data.get('corrosion_rate', 0))
        method = data.get('method', 'asme')
        safety_class = data.get('safety_class', 'medium')
        
        if corrosion_rate < 0:
            return jsonify({'error': 'Corrosion rate cannot be negative'}), 400
        
        if params['defect_depth'] > params['wall_thickness']:
            return jsonify({'error': 'Defect depth cannot exceed wall thickness'}), 400
        
        # Perform calculation based on selected method
        if method == 'asme':
            results = calculate_asme_b31g_modified(**params)
        else:
            results = calculate_dnv_rp_f101(
                params['diameter'], params['wall_thickness'], params['defect_length'], 
                params['defect_depth'], params['smts'], params['maop'], safety_class
            )
        
        # Add remaining life if corrosion rate provided
        if corrosion_rate > 0:
            life_results = calculate_remaining_life(
                params['diameter'], params['wall_thickness'], params['defect_length'],
                params['defect_depth'], params['smys'], params['smts'], params['maop'],
                corrosion_rate, method
            )
            results.update(life_results)
        
        return jsonify(results)
        
    except ValueError:
        return jsonify({'error': 'Invalid data format. Please ensure all fields contain valid numbers'}), 400
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
        'corrosion_rate': 0.1,
        'method': 'asme',
        'safety_class': 'medium'
    }
    return jsonify(example_data)

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    if not os.path.exists('templates'):
        os.makedirs('templates')
        print("Created templates directory")
    
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
# Добавьте это в самый конец файла main.py
if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    if not os.path.exists('templates'):
        os.makedirs('templates')
        print("Created templates directory")
    
    # Use PORT environment variable for Cloud Run, default to 8080 for local
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    print(f"🚀 Starting Pipeline Defect Calculator on port {port}")
    print("📧 Open: http://localhost:8080")
    print("📧 Or: http://127.0.0.1:8080")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
