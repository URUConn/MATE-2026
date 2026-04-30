import math

all_icebergs = []
all_oilrigs = []

iceberg_params = ['long', 'lat', 'heading', 'keel depth']
oilrig_params = ['name', 'long', 'lat', 'water depth']

def gen_iceberg(num_ice):
    iceberg = []
    num_iceberg = num_ice + 1
    print("------------------------------------------")
    print("Iceberg " + str(num_iceberg))

    for x in range(4):
        user_input = float(input("Enter the " + iceberg_params[x] + ": "))
        iceberg.append(user_input)

    all_icebergs.append(iceberg)
    print("------------------------------------------")

def gen_oilrigs(num_oil):
    oilrig = []
    num_oilrig = num_oil + 1
    print("------------------------------------------")
    print("Oilrig "+ str(num_oilrig))

    for x in range(4):
        if x == 0:
            user_input = input("Enter the " + oilrig_params[x] + ": ")
            oilrig.append(user_input)
        else:
            user_input = float(input("Enter the " + oilrig_params[x] + ": "))
            oilrig.append(user_input)
    
    all_oilrigs.append(oilrig)
    print("------------------------------------------")

def object_table(num_ice, num_oil):
    print("------------------------------------------")
    for x in range(num_ice):
        print("Iceberg " + str(x + 1) + ":")
        print("----------")
        for y in range(4):
            print(iceberg_params[y] + ": " + str(all_icebergs[x][y]))
        
    print("----------")

    for x in range(num_oil):
        print("Oilrig " + str(x + 1) + ":")
        print("----------")
        for y in range(4):
            print(oilrig_params[y] + ": " + str(all_oilrigs[x][y]))
    
    print("------------------------------------------")

def distance(iceberg, oilrig):
    x_val = oilrig[1] - iceberg[0]
    y_val = oilrig[2] - iceberg[1]
    dist = math.sqrt((x_val * x_val) + (y_val * y_val))
    return dist

def threat_distance(iceberg, oilrig):
    dist = distance(iceberg, oilrig)

    if dist >= 10:
        iceberg.append(("Green Distance", oilrig[0]))
    elif dist >= 5:
        iceberg.append(("Yellow Distance", oilrig[0]))
    else:
        iceberg.append(("Red Distance", oilrig[0]))

def threat_depth(iceberg, oilrig):
    if iceberg[3] >= oilrig[3] * 1.1:
        iceberg.append(("Green Depth", oilrig[0]))
    elif iceberg[3] >= oilrig[3] * 0.9:
        iceberg.append(("Red Depth", oilrig[0]))
    elif iceberg[3] >= oilrig[3] * 0.7:
        iceberg.append(("Yellow Depth", oilrig[0]))
    else:
        iceberg.append(("Green Depth", oilrig[0]))

def threat_table():
    print("\n------------------------------------------")
    print("Iceberg | Oilrig Name | Threat Distance | Threat Depth")
    print("------------------------------------------")

    for i, iceberg in enumerate(all_icebergs):
        iceberg_name = f"Iceberg {i+1}"

        # threats start at index 4 and come in pairs:
        # [("Distance", rig), ("Depth", rig), ("Distance", rig), ("Depth", rig), ...]
        threats = iceberg[4:]

        # loop through complete threat pairs only; ignore any incomplete trailing entry
        for t in range(0, len(threats) - 1, 2):
            dist_threat = threats[t]
            depth_threat = threats[t+1]

            rig_name = dist_threat[1]
            dist_label = dist_threat[0]
            depth_label = depth_threat[0]

            print(f"{iceberg_name:8} | {rig_name:11} | {dist_label:15} | {depth_label}")

    print("------------------------------------------")

if __name__ == '__main__':
    num_icebergs = int(input("Enter the number of icebergs: "))
    for x in range(num_icebergs):
        gen_iceberg(x)

    num_oilrigs = int(input("Enter the number of oilrigs: "))
    for x in range(num_oilrigs):
        gen_oilrigs(x)

    object_table(num_icebergs, num_oilrigs)

    for x in all_icebergs:
        for y in all_oilrigs:
            threat_distance(x, y)
            threat_depth(x, y)

    threat_table()