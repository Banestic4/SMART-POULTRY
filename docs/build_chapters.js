// Builds Chapter 4 and Chapter 5 draft (ABU CS project guidelines formatting).
// Yellow-highlighted [[...]] text = things only the student can supply (real screenshots, readings, results).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, HeadingLevel, AlignmentType,
  WidthType, LineRuleType, BorderStyle, ShadingType, TabStopType, PageBreak, LevelFormat,
} = require("docx");

const RES = path.join(__dirname, "results");
const FONT = "Times New Roman";
const SZ = 24;            // 12 pt
const TBL_SZ = 21;        // 10.5 pt in tables
const TEXT_W = 8765;      // A4 width minus 3.0 cm left and 2.54 cm right margins, in DXA

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

// ---- inline text with [[placeholder]] highlighting and **bold** ----
function runs(text, extra = {}) {
  const out = [];
  const re = /(\[\[.*?\]\])|(\*\*.*?\*\*)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), font: FONT, size: SZ, ...extra }));
    if (m[1]) out.push(new TextRun({ text: m[1].slice(2, -2), font: FONT, size: SZ, highlight: "yellow", ...extra }));
    else out.push(new TextRun({ text: m[2].slice(2, -2), font: FONT, size: SZ, bold: true, ...extra }));
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), font: FONT, size: SZ, ...extra }));
  return out;
}

const body = (t) => new Paragraph({
  children: runs(t), alignment: AlignmentType.JUSTIFIED,
  spacing: { line: 480, before: 0, after: 0 }, indent: { firstLine: 720 },
});
const bullet = (t) => new Paragraph({
  children: runs(t), numbering: { reference: "bul", level: 0 }, alignment: AlignmentType.JUSTIFIED,
  spacing: { line: 480, before: 0, after: 0 },
});
const chapter = (t) => new Paragraph({
  heading: HeadingLevel.HEADING_1, pageBreakBefore: true, spacing: { line: 360, after: 240 },
  children: [new TextRun({ text: t.toUpperCase(), font: FONT, size: SZ, bold: true })],
});
const h2 = (t) => new Paragraph({
  heading: HeadingLevel.HEADING_2, spacing: { line: 360, before: 240, after: 120 }, keepNext: true,
  children: [new TextRun({ text: t, font: FONT, size: SZ, bold: true })],
});
const h3 = (t) => new Paragraph({
  heading: HeadingLevel.HEADING_3, spacing: { line: 360, before: 120, after: 120 }, keepNext: true,
  children: [new TextRun({ text: t, font: FONT, size: SZ, italics: true })],
});
const caption = (t) => new Paragraph({ children: runs(t, { bold: true }), spacing: { line: 240, before: 200, after: 80 }, keepNext: true });
const figcap = (t) => new Paragraph({ children: runs(t, { bold: true }), alignment: AlignmentType.CENTER, spacing: { line: 240, before: 80, after: 240 } });
const source = (t) => new Paragraph({ children: runs(t, { italics: true, size: 20 }), alignment: AlignmentType.CENTER, spacing: { line: 240, after: 200 } });
const note = (t) => new Paragraph({ children: runs(t, { size: 20 }), spacing: { line: 240, before: 60, after: 200 } });

function figure(file, widthPx) {
  const f = path.join(RES, file);
  const { w, h } = pngSize(f);
  return new Paragraph({
    alignment: AlignmentType.CENTER, keepNext: true, spacing: { line: 240, lineRule: LineRuleType.AUTO, before: 120 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(f), transformation: { width: widthPx, height: Math.round(widthPx * h / w) },
      altText: { title: file, description: file, name: file } })],
  });
}
const placeholderFigure = (t) => new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { line: 240, before: 120, after: 80 }, keepNext: true,
  border: { top: { style: BorderStyle.DASHED, size: 6, color: "999999", space: 12 }, bottom: { style: BorderStyle.DASHED, size: 6, color: "999999", space: 12 },
            left: { style: BorderStyle.DASHED, size: 6, color: "999999", space: 12 }, right: { style: BorderStyle.DASHED, size: 6, color: "999999", space: 12 } },
  children: [new TextRun({ text: t, font: FONT, size: SZ, highlight: "yellow" })],
});

const eq = (t, n) => new Paragraph({
  tabStops: [{ type: TabStopType.CENTER, position: TEXT_W / 2 }, { type: TabStopType.RIGHT, position: TEXT_W }],
  spacing: { line: 360, before: 120, after: 120 },
  children: [new TextRun({ children: ["\t", t, "\t", n], font: FONT, size: SZ })],
});

// ---- tables ----
const thin = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const borders = { top: thin, bottom: thin, left: thin, right: thin };
function table(widths, header, rows) {
  const total = widths.reduce((a, b) => a + b, 0);
  const cell = (t, w, hdr) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders,
    shading: hdr ? { fill: "D9D9D9", type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ spacing: { line: 240 }, children: runs(String(t), { size: TBL_SZ, bold: hdr }) })],
  });
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, widths[i], true)) }),
           ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, widths[i], false)) }))],
  });
}
const gap = () => new Paragraph({ spacing: { line: 240, after: 120 }, children: [] });

// =====================================================================
const C = [];
// ---------------------------------------------------------------- CHAPTER FOUR
C.push(chapter("Chapter Four: System Implementation and Results"));
C.push(h2("4.1 Introduction"));
C.push(body("This chapter presents the implementation of the SMART-Poultry prototype designed in Chapter Three and discusses the results obtained from its testing. It describes the development tools, the hardware and firmware, the backend, database, alert and security components, the training and evaluation of the machine learning models, the user interface, and the tests carried out on the integrated system. The chapter closes with a discussion of the results, including the strengths and weaknesses of the developed system."));
C.push(body("**Deviation from the design.** Chapter Three proposed an ESP32-CAM for image acquisition. The ESP32-CAM module could not be obtained within the project period. The implemented prototype therefore uses an ESP32 development board with a DHT22 temperature and humidity sensor and an MQ135 air-quality sensor. Image analysis was implemented as an image-upload function on the dashboard, and the same interface accepts images posted by a camera module using the device key, so that an ESP32-CAM can be added without changing the backend. This deviation and its consequences are discussed in Section 4.6."));

C.push(h2("4.2 System Implementation"));
C.push(h3("4.2.1 Development Environment and Tools"));
C.push(body("The prototype was developed on a laptop running Windows 10. Table 4.1 lists the tools used and the role of each."));
C.push(caption("Table 4.1: Tools and Technologies Used"));
C.push(table([2600, 6165], ["Tool / Technology", "Role in the system"], [
  ["Arduino IDE with the ESP32 board package", "Writing, compiling and uploading the ESP32 firmware"],
  ["Python 3", "Backend, machine learning and test scripts"],
  ["Flask", "Web framework providing the REST interface, login pages and dashboard"],
  ["SQLite", "Embedded relational database for readings, alerts, images, AI results and users"],
  ["scikit-learn, NumPy, pandas", "Training and running the Logistic Regression and Random Forest models"],
  ["Pillow", "Image validation and feature extraction for the image-analysis module"],
  ["Requests", "Calling the SMS provider's HTTP interface"],
  ["Termii SMS API", "Delivery of SMS alerts to the farmer's phone"],
  ["HTML, CSS and JavaScript", "Browser-based dashboard (charts drawn without external libraries, so the dashboard also works offline)"],
]));
C.push(gap());

C.push(h3("4.2.2 Hardware Implementation"));
C.push(body("The sensing node consists of an ESP32 development board, a DHT22 sensor and an MQ135 module. The DHT22 DATA line is connected to GPIO4 with a 10 kΩ pull-up resistor to 3.3 V. The MQ135 module is powered from the 5 V (VIN) pin because its internal heater requires 5 V. Its analogue output (AO) can reach 5 V, whereas the ESP32 input pins tolerate a maximum of 3.3 V. The AO signal was therefore connected to GPIO34 through a resistive voltage divider formed by a 10 kΩ and a 15 kΩ resistor. The divider output is given by Equation 4.1."));
C.push(eq("Vout = Vin × R2 / (R1 + R2) = 5 × 15 / (10 + 15) = 3.0 V", "4.1"));
C.push(body("GPIO34 belongs to the ADC1 group of the ESP32, which remains usable while Wi-Fi is active, unlike the ADC2 group. Table 4.2 summarises all connections."));
C.push(caption("Table 4.2: Hardware Pin Connections"));
C.push(table([2300, 2300, 4165], ["Component pin", "Connected to", "Purpose"], [
  ["DHT22 pin 1 (VCC)", "ESP32 3V3", "Sensor supply"],
  ["DHT22 pin 2 (DATA)", "ESP32 GPIO4 and 10 kΩ pull-up to 3V3", "Digital temperature and humidity data"],
  ["DHT22 pin 4 (GND)", "ESP32 GND", "Common ground"],
  ["MQ135 VCC", "ESP32 VIN (5 V)", "Heater and sensor supply"],
  ["MQ135 GND", "ESP32 GND", "Common ground"],
  ["MQ135 AO", "10 kΩ, then junction, then 15 kΩ to GND; junction to GPIO34", "Analogue gas reading at a safe voltage"],
]));
C.push(gap());
C.push(figure("wiring_diagram.png", 560));
C.push(figcap("Fig. 4.1: Circuit Connections of the Sensing Node"));
C.push(body("Because the ESP32 board covered all the breadboard holes beside its pins, the board was placed beside the breadboard and connected with jumper wires having a female end. The sensors, resistors and shared ground and supply strips were assembled on the breadboard. Fig. 4.2 shows this arrangement and Fig. 4.3 shows the assembled prototype."));
C.push(figure("layoutB_stage2_full.png", 560));
C.push(figcap("Fig. 4.2: Breadboard Layout of the Prototype"));
C.push(placeholderFigure("[[INSERT a clear photograph of your assembled prototype here (ESP32, breadboard, DHT22, MQ135, wires)]]"));
C.push(figcap("Fig. 4.3: Assembled SMART-Poultry Prototype"));

C.push(h3("4.2.3 Firmware Implementation"));
C.push(body("The firmware was written in the Arduino C++ framework for the ESP32 and uses the Adafruit DHT library. On start-up the firmware configures a 12-bit analogue-to-digital converter with 11 dB attenuation for GPIO34 and connects to the configured Wi-Fi network. Every five seconds it reads the DHT22, averages sixteen MQ135 analogue samples to reduce noise, and builds a JSON message containing the device identifier, temperature, humidity and the raw MQ135 value (0 to 4095). Readings that the DHT22 reports as invalid are discarded, so that incorrect values are never transmitted. The message is sent to the backend with an HTTP POST request that carries a secret device key in the X-API-Key header. The firmware reconnects automatically if the Wi-Fi connection is lost, and the on-board LED flashes when the server confirms receipt. The complete source code is given in Appendix A."));

C.push(h3("4.2.4 Backend Implementation"));
C.push(body("The backend was implemented with Flask. It receives readings from the ESP32, validates them, stores them, applies the alert rules and the machine learning model, and serves the dashboard. A reading is rejected with an error response when a field is missing, is not numeric, or lies outside its physical range (temperature −40 to 80 °C, humidity 0 to 100 %, and MQ135 value 0 to 4095). Table 4.3 lists the interfaces provided."));
C.push(caption("Table 4.3: Backend Interfaces"));
C.push(table([2900, 1700, 4165], ["Route", "Access", "Function"], [
  ["POST /api/readings", "Device key", "Receives, validates and stores a sensor reading; returns the AI risk result and any alerts raised"],
  ["GET /api/latest", "Login", "Latest reading, device online status, thresholds and model status"],
  ["GET /api/history", "Login", "Recent readings for the charts"],
  ["GET /api/alerts", "Login", "Recent alerts with severity and SMS status"],
  ["POST /api/image", "Login or device key", "Validates, stores and classifies an uploaded image"],
  ["GET /api/images", "Login", "Recent images and their predictions"],
  ["POST /api/test-sms", "Login", "Sends a test SMS to verify the notification channel"],
  ["/login and /logout", "Public / session", "User authentication"],
]));
C.push(gap());

C.push(h3("4.2.5 Database Implementation"));
C.push(body("SQLite was used as the database. The five tables proposed in Section 3.7.1 were implemented as shown in Table 4.4."));
C.push(caption("Table 4.4: Database Tables"));
C.push(table([2100, 6665], ["Table", "Main fields"], [
  ["Users", "id, username (unique), password_hash, role, created_at"],
  ["Sensor_Readings", "id, device_id, temperature, humidity, gas_raw, gas_pct, risk_prob, risk_label, created_at"],
  ["Images", "id, filename, source (dashboard or device), created_at"],
  ["AI_Results", "id, kind (environment or image), ref_id, prediction, confidence, created_at"],
  ["Alerts", "id, alert_type, severity, message, reading_id, sms_status, sms_detail, created_at"],
]));
C.push(gap());

C.push(h3("4.2.6 Alert Engine and SMS Notification"));
C.push(body("Each stored reading is compared with configurable thresholds, and the machine learning model produces a probability that the environment is at risk. An alert is raised when any threshold is crossed or when the probability reaches 0.70. Table 4.5 shows the rules. The threshold values are working values for the prototype and can be changed without modifying the code."));
C.push(caption("Table 4.5: Alert Rules"));
C.push(table([2300, 3000, 1300, 2165], ["Alert type", "Condition", "Severity", "Basis"], [
  ["heat_stress", "Temperature ≥ 32 °C", "Critical", "[[cite poultry-housing reference]]"],
  ["cold_stress", "Temperature < 18 °C", "Warning", "[[cite poultry-housing reference]]"],
  ["high_humidity", "Relative humidity > 75 %", "Warning", "[[cite poultry-housing reference]]"],
  ["low_humidity", "Relative humidity < 40 %", "Warning", "[[cite poultry-housing reference]]"],
  ["poor_air_quality", "MQ135 raw value ≥ [[your calibrated limit]]", "Critical", "Calibration in clean air (Section 4.5.2)"],
  ["ai_risk", "Model risk probability ≥ 0.70", "Warning", "Random Forest output"],
]));
C.push(gap());
C.push(body("To prevent repeated messages while a condition persists, an alert of the same type is stored at most once per minute, and an SMS for the same alert type is sent at most once every five minutes. SMS messages are sent through the Termii HTTP interface to one or more configured phone numbers. If the SMS service is not configured or cannot be reached, the alert is still stored and displayed on the dashboard together with the SMS status (sent, failed or skipped) and the reason, so that a communication failure does not stop the monitoring function."));

C.push(h3("4.2.7 Security Implementation"));
C.push(body("The following security measures were implemented:"));
C.push(bullet("Passwords are stored only as salted hashes and are never stored or displayed in plain form."));
C.push(bullet("Access to the dashboard and its data interfaces requires an authenticated session; unauthenticated requests receive an error response or are redirected to the login page."));
C.push(bullet("Session cookies are marked HttpOnly and SameSite, and each response carries protective headers that prevent content-type sniffing and framing."));
C.push(bullet("After five failed sign-in attempts from the same address, further attempts are refused for five minutes, which limits password guessing."));
C.push(bullet("The sensor interface accepts data only from a device that presents the secret device key."));
C.push(bullet("All incoming values are validated, uploaded files are verified to be genuine images, and uploads are limited to 5 MB."));
C.push(bullet("Keys, passwords and phone numbers are supplied through environment variables and are not written into the source code."));
C.push(body("These measures provide the basic level of protection stated in Section 1.7. Communication between the ESP32 and the backend uses HTTP on a local network and is therefore not encrypted, and the device key is a single shared secret. These limitations are discussed in Section 4.6."));

// ---------------------------------------------------------------- 4.3
C.push(h2("4.3 AI Model Training and Testing"));
C.push(h3("4.3.1 Environmental Risk Model"));
C.push(body("As stated in Sections 1.6 and 1.8, simulated environmental data were used at the initial stage because no labelled farm data on disease outcomes were available. A data set of 6,000 samples with three features (temperature, humidity and MQ135 air-quality percentage) was generated from a mixture of operating scenarios: normal operation (50 %), heat (10 %), cold (6 %), high humidity (8 %), low humidity (5 %), high gas (11 %) and combined stress (10 %). Each sample was labelled as normal or at-risk using the rules in Table 4.6, and 3 % of the labels were then flipped at random to represent sensor and labelling uncertainty. About 42.4 % of the samples were labelled at-risk."));
C.push(caption("Table 4.6: Rules Used to Label the Simulated Samples"));
C.push(table([2300, 6465], ["Rule type", "Sample is labelled at-risk when"], [
  ["Single-factor", "Temperature ≥ 32 °C or < 18 °C; humidity > 75 % or < 40 %; or air-quality percentage > 53.7 %"],
  ["Compound", "Temperature > 29 °C and humidity > 70 %; or air-quality > 45 % and humidity > 70 %; or temperature > 30 °C and air-quality > 45 %"],
]));
C.push(gap());
C.push(body("The data were divided into 80 % for training (4,800 samples) and 20 % for testing (1,200 samples) using stratified sampling, and five-fold cross-validation was applied to the training portion. Three classifiers were compared: Logistic Regression on the raw features; Logistic Regression on deviation features (the distance of temperature and humidity from the centre of their comfortable range); and a Random Forest of 200 trees with a maximum depth of 10 (Breiman, 2001). All were implemented with scikit-learn (Pedregosa et al., 2011). Class weights were balanced for all models. Table 4.7 gives the test-set results and Fig. 4.4 shows the confusion matrices."));
C.push(caption("Table 4.7: Performance of the Environmental Risk Models on the Test Set"));
C.push(table([2900, 1100, 1100, 1000, 1000, 1000, 665 + 0], ["Model", "Accuracy", "Precision", "Recall", "F1-score", "ROC-AUC", "CV F1"], [
  ["Logistic Regression (raw features)", "0.668", "0.629", "0.529", "0.574", "0.673", "0.591"],
  ["Logistic Regression (deviation features)", "0.884", "0.844", "0.892", "0.867", "0.937", "0.869"],
  ["Random Forest", "0.958", "0.962", "0.939", "0.950", "0.959", "0.955"],
]));
C.push(note("CV F1 = mean five-fold cross-validation F1-score on the training data. Values are taken from docs/results/env_metrics.json. [[If you retrain on your laptop, copy the new values from your own env_metrics.json]]"));
C.push(figure("confusion_matrices.png", 590));
C.push(figcap("Fig. 4.4: Confusion Matrices of the Three Models on the Test Set"));
C.push(body("Logistic Regression on the raw features performed poorly (F1-score 0.574) because the risk is two-sided: both low and high temperature, and both low and high humidity, are unfavourable, so no single straight decision boundary separates the classes. When deviation features were supplied, the same linear model improved to an F1-score of 0.867, which confirms this explanation. The Random Forest, which can represent such non-linear and interacting conditions without hand-made features, achieved the best result (accuracy 95.8 %, precision 96.2 %, recall 93.9 %, F1-score 0.950) and was therefore deployed in the system. Its estimated feature importances were 0.377 for temperature, 0.375 for humidity and 0.248 for air quality (Fig. 4.5)."));
C.push(figure("feature_importance.png", 330));
C.push(figcap("Fig. 4.5: Random Forest Feature Importance"));
C.push(body("**Interpretation and limitation.** The high scores must be interpreted carefully. The labels were produced from housing-condition rules, so the model has learned an approximation of those rules; the results show that the model can reproduce and generalise the risk rules from noisy data, not that it can predict disease outbreaks. Validation against real labelled farm records is required before the model can be presented as a disease predictor. This is stated as a limitation in Section 4.6 and as a recommendation in Chapter Five."));

C.push(h3("4.3.2 Image Classification Module"));
C.push(body("The image module was implemented as a classical computer-vision pipeline. Each image is resized to 128 × 128 pixels and described by an HSV colour histogram (8 × 4 × 4 bins), a nine-bin gradient-orientation histogram of the grey image (texture and edges), and the mean and standard deviation of each colour channel. A Random Forest classifier is trained on these features. The same feature extractor is used during training and during use in the backend, so that predictions are consistent. When a prediction other than a healthy or normal class is made with a confidence of at least 60 %, an alert is raised."));
C.push(body("[[Choose ONE of the following paragraphs and delete the other.]]"));
C.push(body("[[IF you trained the model: The module was trained on the [dataset name and source], containing [N] images in [K] classes ([list classes]). Of these, [n_train] were used for training and [n_test] for testing. Table 4.8 gives the results. Paste the numbers from docs/results/cv_metrics.json and the confusion matrix from docs/results/cv_confusion_matrix.png.]]"));
C.push(body("[[IF you did NOT train it: The image module was implemented and tested for correct operation (image upload, validation, storage and the prediction pathway), but it was not trained or evaluated on a poultry disease data set within the project period. No accuracy figures are therefore reported for it, and it is presented as a framework for future work.]]"));

// ---------------------------------------------------------------- 4.4
C.push(h2("4.4 User Interface Design"));
C.push(body("The user interface consists of a login page and a dashboard. The login page (Fig. 4.6) accepts a username and password and shows an error message when the details are invalid or when the sign-in has been temporarily locked."));
C.push(placeholderFigure("[[INSERT screenshot of the login page]]"));
C.push(figcap("Fig. 4.6: Login Interface"));
C.push(body("The dashboard (Fig. 4.7) refreshes every three seconds and presents four status cards (temperature, humidity, MQ135 air-quality index and AI risk assessment), each coloured green, amber or red according to the thresholds; a device status indicator that shows ONLINE or OFFLINE depending on when the last reading arrived; line charts of recent temperature, humidity and air-quality values; a list of alerts with their severity and SMS status; a button for sending a test SMS; and an image-analysis panel with thumbnails of recent images and their predictions. The layout adapts to narrow screens so that it can be used on a phone."));
C.push(placeholderFigure("[[INSERT screenshot of the dashboard showing REAL readings from your sensors]]"));
C.push(figcap("Fig. 4.7: Dashboard Interface"));
C.push(placeholderFigure("[[INSERT screenshot of the dashboard with an alert displayed and its SMS status]]"));
C.push(figcap("Fig. 4.8: Alert Notification on the Dashboard"));
C.push(placeholderFigure("[[INSERT photograph or screenshot of the SMS received on the phone (if SMS delivery was achieved)]]"));
C.push(figcap("Fig. 4.9: SMS Alert Received on the Farmer's Phone"));

// ---------------------------------------------------------------- 4.5
C.push(h2("4.5 System Testing"));
C.push(h3("4.5.1 Software and Interface Tests"));
C.push(body("An automated test suite was written to exercise the backend through its HTTP interface, following the plan in Section 3.10.3. Table 4.9 lists the tests, the expected results and the observed results."));
C.push(caption("Table 4.9: Software and Security Test Cases"));
const OBS = "[[Pass / Fail]]";
C.push(table([700, 4000, 2865, 1200], ["ID", "Test", "Expected result", "Observed"], [
  ["T01", "Reading sent without a device key", "Rejected (401)", OBS],
  ["T02", "Reading sent with a wrong device key", "Rejected (401)", OBS],
  ["T03", "Non-numeric temperature value", "Rejected (400)", OBS],
  ["T04", "Humidity outside 0 to 100 %", "Rejected (400)", OBS],
  ["T05", "Valid normal reading", "Stored (201), classified normal", OBS],
  ["T06", "Normal reading", "No threshold alert raised", OBS],
  ["T07", "High-temperature reading", "Accepted; heat-stress alert stored", OBS],
  ["T08", "High MQ135 reading", "Accepted; air-quality alert stored", OBS],
  ["T09", "Dashboard data requested without login", "Refused (401)", OBS],
  ["T10", "Dashboard page requested without login", "Redirected to the login page", OBS],
  ["T11", "Sign-in with valid credentials", "Access granted", OBS],
  ["T12", "Latest reading after login", "Reading returned", OBS],
  ["T13", "History after login", "Readings returned", OBS],
  ["T14", "Alerts after login (heat, air quality, AI risk)", "All three alert types present", OBS],
  ["T15", "Upload a valid image", "Accepted and stored", OBS],
  ["T16", "Upload a non-image file", "Rejected (400)", OBS],
  ["T17", "Upload an image without login or device key", "Rejected (401)", OBS],
  ["T18", "Seven consecutive wrong passwords", "Temporary lock-out message", OBS],
]));
C.push(note("Run the suite on your laptop (python test_system.py --password YOUR_PASSWORD) and record the result of each test. Test T14 is reported by the script as four checks (T14, T14b, T14c, T14d). [[State the total, e.g. 21 of 21 checks passed]]"));

C.push(h3("4.5.2 Hardware and Calibration Tests"));
C.push(body("Each sensor was first tested alone through the Serial Monitor of the Arduino IDE, and then together with the network connection. The DHT22 readings were compared with a reference thermometer or phone reading taken at the same time. The MQ135 was left to warm up and its clean-air baseline was recorded; an alcohol vapour source was then brought near the sensor to confirm that the reading rose, and the air-quality alert limit was set between the two values."));
C.push(caption("Table 4.10: Hardware Test Results"));
C.push(table([2600, 2000, 2000, 2165], ["Test", "Reference value", "Prototype reading", "Remark"], [
  ["DHT22 temperature (room)", "[[__ °C]]", "[[__ °C]]", "[[difference]]"],
  ["DHT22 humidity (room)", "[[__ %]]", "[[__ %]]", "[[difference]]"],
  ["MQ135 clean-air baseline (raw)", "not applicable", "[[__]]", "After [[__]] minutes warm-up"],
  ["MQ135 with alcohol vapour (raw)", "not applicable", "[[__]]", "Reading rose as expected [[yes/no]]"],
]));
C.push(gap());

C.push(h3("4.5.3 Communication and Integration Tests"));
C.push(body("The complete data path was tested from the sensors to the dashboard: the ESP32 connected to a smartphone hotspot, posted readings to the backend running on the laptop, and the dashboard displayed them. [[State the observed delay between a change at the sensor and its appearance on the dashboard, e.g. about 5 seconds, and how long you ran the system continuously.]] To test the alert path in a controlled way, abnormal conditions were produced by warming the DHT22 slightly and by exposing the MQ135 to alcohol vapour. [[State which alerts were triggered.]]"));
C.push(body("A sensor simulator that posts readings through the same interface as the ESP32 was also used during development, and to demonstrate alert scenarios that cannot safely be created with live birds, such as sustained heat stress. Results obtained from the simulator are identified as simulated wherever they are reported."));

C.push(h3("4.5.4 Notification Test"));
C.push(body("[[Describe your real SMS test: the provider (Termii), the route used, the time taken from alert to SMS arrival, and whether the SMS arrived. If SMS delivery did not work, say so plainly and state the cause shown in the alert list (for example sender ID not approved, route not activated or no credit). Do not claim delivery that was not observed.]]"));

// ---------------------------------------------------------------- 4.6
C.push(h2("4.6 Results and Discussion"));
C.push(body("Table 4.11 relates the results to the objectives stated in Section 1.3.2."));
C.push(caption("Table 4.11: Achievement of the Project Objectives"));
C.push(table([3300, 1500, 3965], ["Objective", "Status", "Evidence"], [
  ["1. IoT system for temperature and humidity data", "Achieved", "ESP32 with DHT22 and MQ135 sending data over Wi-Fi (Sections 4.2.2, 4.2.3, 4.5.2)"],
  ["2. Computer-vision model for poultry images", "Partly achieved", "Upload, storage and classification pipeline implemented; [[state training status]]; no live camera"],
  ["3. Machine learning for abnormal conditions and risk", "Achieved on simulated data", "Random Forest, F1-score 0.950 (Section 4.3.1); not validated on real disease data"],
  ["4. Real-time alerts by dashboard and SMS", "Achieved for the dashboard; SMS [[state result]]", "Sections 4.2.6, 4.4 and 4.5.4"],
  ["5. Secure authentication and access control", "Achieved at a basic level", "Section 4.2.7 and tests T09 to T18"],
  ["6. Evaluation with simulated and real-world data", "Achieved within limits", "Real sensor readings from a room environment and simulated data for the models; no farm trial"],
]));
C.push(gap());
C.push(h3("4.6.1 Strengths of the System"));
C.push(bullet("The system works end to end: real sensor readings reach the dashboard and trigger alerts within seconds."));
C.push(bullet("The low-cost hardware and open-source software make the design affordable for small farms."));
C.push(bullet("Alerts continue to be recorded and displayed even if SMS or the model is unavailable, and an offline indicator shows when the sensor node stops reporting."));
C.push(bullet("The modular design allows a camera, extra sensors or a better model to be added without redesigning the platform."));
C.push(bullet("The security measures protect access and data integrity at a basic level, and the automated test suite makes the behaviour repeatable."));
C.push(h3("4.6.2 Weaknesses and Limitations"));
C.push(bullet("No camera was used, so live image acquisition from the poultry house was not implemented, which departs from the design in Chapter Three."));
C.push(bullet("The machine learning models were trained on simulated data with rule-based labels, so they do not demonstrate real disease prediction."));
C.push(bullet("The MQ135 gives a relative air-quality indication that is affected by temperature, humidity and warm-up time; it is not a calibrated ammonia measurement."));
C.push(bullet("Data travel over unencrypted HTTP on a local network and the device key is shared, so the system is suitable for a prototype, not for the open internet."));
C.push(bullet("SMS delivery depends on the provider account, an approved sender ID, the chosen route and network conditions."));
C.push(bullet("The prototype was tested with one sensor node in a room and not with birds on a farm, and the alert thresholds are working values that need validation by a poultry specialist."));

// ---------------------------------------------------------------- CHAPTER FIVE
C.push(chapter("Chapter Five: Summary, Conclusion and Recommendations"));
C.push(h2("5.1 Summary"));
C.push(body("This project set out to develop a secure, AI-based poultry monitoring system that combines Internet of Things sensing, machine learning, computer vision, a web dashboard and SMS alerting. Chapter One stated the problem, the aim and objectives, and the scope. Chapter Two reviewed the literature on smart agriculture, IoT, artificial intelligence and computer vision in poultry monitoring, and identified the need for an integrated, low-cost platform. Chapter Three presented the design of the system. Chapter Four described the implementation and testing of a working prototype."));
C.push(body("The prototype uses an ESP32 with a DHT22 and an MQ135 sensor to measure temperature, humidity and air quality, and sends the readings over Wi-Fi to a Flask backend with an SQLite database. A Random Forest model trained on simulated environmental data achieved an F1-score of 0.950 on a held-out test set, and was used to estimate the probability that conditions are at risk. A password-protected dashboard displays live readings, history, alerts and image-analysis results, and alerts are sent by SMS through a commercial SMS interface. [[Add one sentence on how the real-hardware testing went.]]"));
C.push(h2("5.2 Conclusion"));
C.push(body("The project demonstrated that a low-cost sensing node, an open-source backend and a simple machine learning model can be combined into a working poultry-house monitoring and early-warning prototype. The objectives on data acquisition, environmental risk modelling, real-time alerting and basic security were achieved, while the computer-vision objective was achieved only in part because no camera module and no trained disease data set were available within the project period. The system should therefore be regarded as a decision-support prototype that gives early warning of unfavourable environmental conditions, and not as a diagnostic tool for poultry disease."));
C.push(h2("5.3 Recommendations"));
C.push(body("The following recommendations are made for further work:"));
C.push(bullet("Add an ESP32-CAM module so that images are captured automatically and sent to the existing image interface."));
C.push(bullet("Train the image model on a larger, labelled poultry data set collected locally, and compare the present feature-based method with a convolutional neural network or transfer learning."));
C.push(bullet("Collect real environmental and flock-health records from a poultry farm so that the risk model can be trained and validated on real outcomes."));
C.push(bullet("Calibrate the gas sensing against a reference instrument, or use a dedicated ammonia sensor, and have the alert thresholds reviewed by a poultry veterinarian."));
C.push(bullet("Secure the communication with HTTPS or MQTT over TLS, give each device its own key, and move the backend to a cloud server so that the system can be reached beyond the local network."));
C.push(bullet("Support several sensor nodes and houses, add local data storage on the ESP32 for network outages, and develop a mobile application for farmers."));
C.push(bullet("Extend the system with actuators such as fans or heaters that respond automatically to alerts."));

// ---------------------------------------------------------------- reference additions
C.push(new Paragraph({ children: [new PageBreak()] }));
C.push(new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { line: 360, after: 120 },
  children: [new TextRun({ text: "NOTES FOR THE STUDENT (delete this page before submission)", font: FONT, size: SZ, bold: true, highlight: "yellow" })] }));
const sn = (t) => new Paragraph({ children: runs(t, { size: 22 }), spacing: { line: 276, after: 120 } });
C.push(sn("**1. References to add to your reference list (APA, alphabetical):**"));
C.push(sn("Breiman, L. (2001). Random forests. Machine Learning, 45(1), 5–32."));
C.push(sn("Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., … Duchesnay, É. (2011). Scikit-learn: Machine learning in Python. Journal of Machine Learning Research, 12, 2825–2830."));
C.push(sn("**2.** Replace every yellow [[...]] item with your own real result, screenshot or photograph. Delete any sentence you cannot support with something you actually observed."));
C.push(sn("**3.** Table and figure numbers follow the guidelines (Table 4.1, Fig. 4.1 ...). The table of contents, list of figures and list of tables in your main document must be updated to match, and the tables numbered 4.8 to 4.11 in the text may need renumbering if you add or remove any."));
C.push(sn("**4.** Typed equation 4.1 should be retyped with the Word equation editor, as the guidelines require."));
C.push(sn("**5.** Appendix A (firmware and source code) must start on a new page after the references."));

const doc = new Document({
  creator: "SMART-Poultry project", title: "SMART-Poultry Chapters 4 and 5 (draft)",
  styles: {
    default: { document: { run: { font: FONT, size: SZ } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: SZ, bold: true }, paragraph: { spacing: { line: 360 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: SZ, bold: true }, paragraph: { spacing: { line: 360 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: SZ, italics: true }, paragraph: { spacing: { line: 360 }, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, bottom: 1440, right: 1440, left: 1701 } } },
    children: C,
  }],
});
Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, "Chapter_4_and_5_DRAFT.docx");
  fs.writeFileSync(out, buf);
  console.log("written", out);
});
