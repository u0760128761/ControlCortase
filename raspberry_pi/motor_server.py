import socket
import RPi.GPIO as GPIO
import time

# --- GPIO Configuration (L298N) ---
# Adjust these pins according to your wiring
ENA = 25  # PWM Speed Motor 1
IN1 = 23  # Motor 1 Direction A
IN2 = 24  # Motor 1 Direction B

ENB = 18  # PWM Speed Motor 2
IN3 = 17  # Motor 2 Direction A
IN4 = 27  # Motor 2 Direction B

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(ENA, GPIO.OUT)
GPIO.setup(IN1, GPIO.OUT)
GPIO.setup(IN2, GPIO.OUT)

GPIO.setup(ENB, GPIO.OUT)
GPIO.setup(IN3, GPIO.OUT)
GPIO.setup(IN4, GPIO.OUT)

# Setup PWM
pwm_m1 = GPIO.PWM(ENA, 1000) # 1kHz
pwm_m2 = GPIO.PWM(ENB, 1000)
pwm_m1.start(0)
pwm_m2.start(0)

current_speed = 50 # Default 0-100 duty cycle (will map from 0-255 input)

def map_speed(val):
    # App sends 0-255, RPi.GPIO PWM expects 0-100
    duty = (val / 255.0) * 100
    return max(0, min(100, duty))

def set_motor(motor, state):
    if motor == 1:
        if state == "FORWARD":
            GPIO.output(IN1, GPIO.HIGH)
            GPIO.output(IN2, GPIO.LOW)
        elif state == "BACKWARD":
            GPIO.output(IN1, GPIO.LOW)
            GPIO.output(IN2, GPIO.HIGH)
        elif state == "STOP":
            GPIO.output(IN1, GPIO.LOW)
            GPIO.output(IN2, GPIO.LOW)
    elif motor == 2:
        if state == "FORWARD":
            GPIO.output(IN3, GPIO.HIGH)
            GPIO.output(IN4, GPIO.LOW)
        elif state == "BACKWARD":
            GPIO.output(IN3, GPIO.LOW)
            GPIO.output(IN4, GPIO.HIGH)
        elif state == "STOP":
            GPIO.output(IN3, GPIO.LOW)
            GPIO.output(IN4, GPIO.LOW)

def server_loop():
    # Use standard socket instead of PyBluez
    server_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    
    # Bind to any adapter on channel 1
    # Check if we need to release the port or reuse address
    # server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Generally not needed for RFCOMM in the same way
    
    try:
        server_sock.bind((socket.BDADDR_ANY, 1))
    except PermissionError:
        print("Error: Permission denied. Try running with sudo.")
        return
    except OSError as e:
        print(f"Error binding to port: {e}")
        return

    server_sock.listen(1)

    port = 1 # We explicitly bound to channel 1
    
    print(f"Waiting for connection on RFCOMM channel {port}...")
    print("Ensure your Android app is connecting to this device's MAC address on UUID/Channel 1")
    
    # NOTE: advertise_service is removed as it caused issues and SD is strictly not necessary if we connect by MAC
    
    while True:
        try:
            client_sock, client_info = server_sock.accept()
            print("Accepted connection from", client_info)
            
            try:
                while True:
                    data = client_sock.recv(1024)
                    if not data:
                        break
                    
                    try:
                        cmd_str = data.decode("utf-8").strip()
                    except:
                        print("Decode error")
                        continue
                        
                    print("Received:", cmd_str)
                    
                    # Protocol Handling
                    if cmd_str == "M1_FORWARD":
                        set_motor(1, "FORWARD")
                    elif cmd_str == "M1_BACKWARD":
                        set_motor(1, "BACKWARD")
                    elif cmd_str == "M1_STOP":
                        set_motor(1, "STOP")
                    elif cmd_str == "M2_FORWARD":
                        set_motor(2, "FORWARD")
                    elif cmd_str == "M2_BACKWARD":
                        set_motor(2, "BACKWARD")
                    elif cmd_str == "M2_STOP":
                        set_motor(2, "STOP")
                    elif cmd_str.startswith("SPEED:"):
                        try:
                            val = int(cmd_str.split(":")[1])
                            duty = map_speed(val)
                            pwm_m1.ChangeDutyCycle(duty)
                            pwm_m2.ChangeDutyCycle(duty)
                            print(f"Speed set to {duty}%")
                        except ValueError:
                            print("Invalid Speed Value")
                    
            except IOError:
                print("Connection disconnected")
            
            client_sock.close()
            print("Client closed. Waiting for new connection...")
            # Stop motors on disconnect for safety
            set_motor(1, "STOP")
            set_motor(2, "STOP")
            
        except KeyboardInterrupt:
            print("Stopping Server")
            break
        except Exception as e:
             print(f"Error accepting connection: {e}")

    server_sock.close()
    GPIO.cleanup()

if __name__ == "__main__":
    server_loop()
