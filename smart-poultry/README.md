# SMART-Poultry - Build and Run Guide (Windows 10)

Pipeline: **DHT22 + MQ135 -> ESP32 -> Wi-Fi (phone hotspot) -> Flask backend + SQLite -> AI risk model -> dashboard + SMS**

```
smart-poultry/
  firmware/smart_poultry/smart_poultry.ino   ESP32 code
  backend/                                    Flask app (app.py), login, DB, SMS, AI
  ml/train_models.py                          Logistic Regression + Random Forest (simulated data)
  ml/train_cv.py                              Image classifier (needs YOUR image dataset)
  tools/simulator.py                          Fake sensor (testing / safety net)
  tools/test_system.py                        21 automated checks (use in Chapter 4)
  docs/results/                               wiring diagram, metrics, figures
```

## STEP 1 - Wire the hardware (USB unplugged)

Your ESP32 stays OFF the breadboard. Use **female-to-male** Dupont wires: the female end goes on the ESP32 / MQ135 pin, the male end goes into the breadboard hole. Find every pin by the **label printed on the board**.

* Stage 1 (ESP32 + DHT22): follow `docs/results/layoutB_stage1_dht22.png`. Upload the firmware and confirm temperature/humidity in the Serial Monitor BEFORE continuing.
* Stage 2 (add MQ135): follow `docs/results/layoutB_stage2_full.png`.

| Wire | Male end (breadboard hole) | Female end (board pin) |
|---|---|---|
| 1 | a8 | ESP32 3V3 |
| 2 | a11 | ESP32 GND |
| 3 | a9 | ESP32 D4 (GPIO4) |
| 4 | 10k resistor standing upright, b8 to b9 | (DATA pull-up to 3V3) |
| 5 | a14 | ESP32 VIN (5 V) |
| 6 | b14 | MQ135 VCC |
| 7 | b11 | MQ135 GND |
| 8 | a3 | MQ135 AO |
| 9 | 10k resistor b3 to b7 | (divider, top) |
| 10 | 15k resistor c7 to c11 | (divider, bottom to GND) |
| 11 | a7 | ESP32 D34 (GPIO34) |

DHT22 (grille facing you, pins down) goes in row e of strips 8-11: pin 1 VCC, 2 DATA, 3 unused, 4 GND.

* The divider keeps GPIO34 at about 3.0 V. **Never connect MQ135 AO straight to the ESP32** (it can output up to 5 V).
* The ESP32 pin positions in my pictures follow the common 30-pin DOIT DevKit V1 layout from memory; if your board differs, go by the printed labels.
* MQ135 needs several minutes of warm-up. Its reading is a relative air-quality indicator, not calibrated ammonia.
* `docs/results/wiring_diagram.png` is the electrical schematic (for the report).

## STEP 2 - Arduino IDE

1. File > Preferences > "Additional boards manager URLs" is only needed for old versions; normally open **Tools > Board > Boards Manager**, search `esp32`, install **esp32 by Espressif Systems**.
2. **Tools > Manage Libraries**: install **DHT sensor library** (Adafruit) and, when asked, **Install all** (Adafruit Unified Sensor).
3. Tools > Board: **ESP32 Dev Module**. Plug in the USB, choose the **Port**. If no port appears, install the CP210x or CH340 USB driver (look at the small chip near the USB socket).
4. Open `firmware/smart_poultry/smart_poultry.ino`, edit the 4 lines under USER SETTINGS (Step 4 tells you the server IP). Upload. Open Serial Monitor at **115200** baud.

## STEP 3 - Backend on the laptop

Open Command Prompt in the `smart-poultry` folder:

```
cd backend
pip install -r requirements.txt
python ..\ml\train_models.py        (retrains the AI model with your own library versions)
python create_user.py admin          (choose a password, 8+ characters)
```

## STEP 4 - Network (the most common demo failure)

1. Turn on your phone hotspot. Connect the **laptop** to it, and the ESP32 will join the same hotspot.
2. On the laptop run `ipconfig`, read the **IPv4 Address** of the Wi-Fi adapter (for example `192.168.43.100`; yours will differ). Put it in the firmware: `http://<that IP>:5000/api/readings`. Re-upload.
3. Allow the port through Windows Firewall (Command Prompt as Administrator):
   `netsh advfirewall firewall add rule name="SmartPoultry" dir=in action=allow protocol=TCP localport=5000`
4. The laptop IP can change when the hotspot restarts. Re-check with `ipconfig` before the defence.

## STEP 5 - Run it

```
cd backend
python app.py
```
Open `http://localhost:5000`, sign in. The status pill turns green (ONLINE) when the ESP32 is posting.

**No hardware yet?** In another Command Prompt: `python tools\simulator.py --scenario cycle` (scenarios: normal, heat, cold, humid, gas, mixed). If you ever use it in the defence, **say it is simulated data**.

Run the tests: `python tools\test_system.py --password <your password>` (it deliberately triggers the login lock-out, which then lasts 5 minutes for that machine; restart `app.py` to clear it).

## STEP 6 - SMS alerts (Termii)

Set these in the same Command Prompt **before** `python app.py` (they are not saved in the code):

```
set SP_SMS_API_KEY=your_termii_api_key
set SP_SMS_BASE_URL=https://api.ng.termii.com        (use the base URL shown on YOUR Termii dashboard)
set SP_SMS_SENDER_ID=YourApprovedSenderID
set SP_SMS_RECIPIENTS=2348012345678                  (international format, no +)
set SP_SMS_CHANNEL=dnd
```
Then click **Send test SMS** on the dashboard. Notes from Termii's documentation:
* `generic` is the promotional route: it does not deliver to numbers on Do Not Disturb, and MTN blocks it between 8 PM and 8 AM. `dnd` has no such restriction, but it must be activated on the account (Termii support).
* A sender ID must be 3-11 characters and generally needs approval; you also need SMS credit on the account.
* I tested the SMS code against a **mock** Termii server only, not the real service. Your first real test tonight will show whether your account, sender ID and route work. If it fails, send me the message shown next to "SMS:" in the alert list.
* If SMS cannot be made to work in time: alerts, their severity and SMS status are still logged and shown on the dashboard. Say honestly that SMS delivery depends on the provider account, and show a screen recording of any successful test.

## Calibrating the MQ135 (5 minutes, matters for your demo)

1. Power the sensor for at least 10 minutes in a normal room. Watch `MQ135 raw=` in the Serial Monitor. Note the steady value (the clean-air baseline).
2. Bring a small amount of a safe gas source close to it (a cotton bud with a little hand sanitizer / alcohol, or a recently struck match held at a distance). Note the raised value.
3. Set the alert limit between the two: `set SP_GAS_HIGH_RAW=<value>` before `python app.py`. (Default 2200 is only a placeholder.)

## Image analysis (no ESP32-CAM)

The dashboard accepts an uploaded image and classifies it. This needs a trained model, which needs a labelled image dataset:
1. Download a public poultry disease image dataset on a computer with internet (search Kaggle for "poultry disease images"; I could not download one from my workspace).
2. Arrange it as `ml/dataset/<class_name>/*.jpg` and run `python ml\train_cv.py`.
3. Restart `app.py`. Without a trained model, the dashboard still stores the image and says the model is not trained.
Be precise in the defence: this module is classical feature-based computer vision, not a CNN.

## Pre-defence checklist

- [ ] Laptop charged; charger in the bag; phone hotspot on with data and battery
- [ ] `ipconfig` IP matches the one in the firmware
- [ ] ESP32 powered from a power bank or the laptop USB
- [ ] Backend running, dashboard logged in, a **recorded backup video** of the full flow on your phone
- [ ] Printed or PDF report, plus the source code appendix
