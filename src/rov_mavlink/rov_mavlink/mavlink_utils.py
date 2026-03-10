"""

    return mode_names.get(custom_mode, f'UNKNOWN({custom_mode})')
    }
        24: 'GUIDED_NOGPS',
        23: 'AVOID_ADSB',
        22: 'THROW',
        21: 'BRAKE',
        20: 'POS_HOLD',
        19: 'AUTOTUNE',
        18: 'FLIP',
        17: 'SPORT',
        15: 'GUIDED',
        14: 'LAND',
        12: 'LOITER',
        11: 'RTL',
        10: 'AUTO',
        8: 'AUTOTUNE',
        7: 'CRUISE',
        6: 'FBWB',
        5: 'FBWA',
        4: 'ACRO',
        3: 'TRAINING',
        2: 'STABILIZE',
        1: 'CIRCLE',
        0: 'MANUAL',
    mode_names = {
    """Get human-readable flight mode string from MAVLink mode values"""
def get_flight_mode_string(base_mode, custom_mode):


    return (pwm_value - 1500) / 400.0
    """
        Normalized value (-1.0 to 1.0)
    Returns:

        pwm_value: PWM value in microseconds (1100-1900)
    Args:

    Convert PWM microseconds to normalized value (-1.0 to 1.0).
    """
def pwm_to_normalize(pwm_value):


    return int(pwm)
    pwm = 1500 + (value * 400)
    value = max(-1.0, min(1.0, value))  # Clamp
    """
        PWM value in microseconds (1100-1900, with 1500 as neutral)
    Returns:

        value: Thruster command (-1.0 = full reverse, 0.0 = neutral, 1.0 = full forward)
    Args:

    Convert normalized thruster value (-1.0 to 1.0) to PWM microseconds.
    """
def normalize_to_pwm(value):


from pymavlink.dialects.v10 import ardusub as mavlink_module

"""
MAVLink utilities for ArduSub communication
