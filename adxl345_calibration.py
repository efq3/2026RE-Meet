import time
import board
import busio
import adafruit_tca9548a
import adafruit_adxl34x

# Target MUX channel for calibration (0, 1, 2, or 3)
TARGET_CH = 0

def main():
    # Initialize I2C and multiplexer
    i2c = busio.I2C(board.SCL, board.SDA)
    tca = adafruit_tca9548a.TCA9548A(i2c)
    
    try:
        sensor = adafruit_adxl34x.ADXL345(tca[TARGET_CH])
    except Exception as e:
        print(f"CH{TARGET_CH} Cannot find sensor. Please check the wiring: {e}")
        return

    print(f"=== CH{TARGET_CH} ADXL345 Calibration Start ===")
    print("The Adafruit library outputs data in m/s^2.\n")
    measurements = {}
    
    orientations = [
        ('Z', '+1g (Place the sensor flat)'),
        ('Z', '-1g (Flip the sensor upside down)'),
        ('X', '+1g (X-axis arrow pointing down)'),
        ('X', '-1g (X-axis arrow pointing up)'),
        ('Y', '+1g (Y-axis arrow pointing down)'),
        ('Y', '-1g (Y-axis arrow pointing up)')
    ]

    for axis, desc in orientations:
        input(f"[{axis}-axis measurement] Place it as {desc} and press Enter...")
        print("Collecting data...")
        
        # Calculate average after 100 measurements
        x_sum, y_sum, z_sum = 0, 0, 0
        for _ in range(100):
            x, y, z = sensor.acceleration
            x_sum += x
            y_sum += y
            z_sum += z
            time.sleep(0.01)
            
        avg_x = x_sum / 100
        avg_y = y_sum / 100
        avg_z = z_sum / 100
        
        # Save principal axis data
        if axis == 'X' and '+1g' in desc: measurements['X_MAX'] = avg_x
        elif axis == 'X' and '-1g' in desc: measurements['X_MIN'] = avg_x
        elif axis == 'Y' and '+1g' in desc: measurements['Y_MAX'] = avg_y
        elif axis == 'Y' and '-1g' in desc: measurements['Y_MIN'] = avg_y
        elif axis == 'Z' and '+1g' in desc: measurements['Z_MAX'] = avg_z
        elif axis == 'Z' and '-1g' in desc: measurements['Z_MIN'] = avg_z
        
        print(f"Done! Measured values: X={avg_x:.2f}, Y={avg_y:.2f}, Z={avg_z:.2f}\n")

    # Calculate offset: (Max + Min) / 2
    offset_x = (measurements['X_MAX'] + measurements['X_MIN']) / 2.0
    offset_y = (measurements['Y_MAX'] + measurements['Y_MIN']) / 2.0
    offset_z = (measurements['Z_MAX'] + measurements['Z_MIN']) / 2.0

    print(f"=== CH{TARGET_CH} Calibration Complete ===")
    print(f"Calculated offset values: ({offset_x:.3f}, {offset_y:.3f}, {offset_z:.3f})")
    print(f"\nPlease update the value of key {TARGET_CH} in the self.offsets dictionary of your existing class with the above result.")

if __name__ == '__main__':
    main()