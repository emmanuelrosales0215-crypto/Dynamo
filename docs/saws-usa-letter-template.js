// Generator for docs/saws-usa-letter-template.docx (SAWS Utility Service Agreement request letter).
// Regenerate:  npm install docx && node docs/saws-usa-letter-template.js docs/saws-usa-letter-template.docx
// The .docx is the deliverable; this script is kept so the template stays reviewable in git.
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, AlignmentType,
  LevelFormat, convertInchesToTwip,
} = require("docx");

const P = "[   ]";            // house placeholder convention
const FONT = "Times New Roman";

// ---- helpers ---------------------------------------------------------------

// Plain body paragraph (no list numbering), optionally indented.
const body = (text, opts = {}) =>
  new Paragraph({
    style: "Normal (Web)",
    spacing: { after: opts.after === undefined ? 200 : opts.after },
    indent: opts.indent ? { left: convertInchesToTwip(opts.indent) } : undefined,
    alignment: opts.align,
    children: [new TextRun({ text, bold: !!opts.bold, allCaps: !!opts.caps })],
  });

// Numbered item at level 0 -> "1." / level 1 -> "a."
const item = (level, runs, opts = {}) =>
  new Paragraph({
    style: "Normal (Web)",
    numbering: { reference: "usa-list", level },
    spacing: { after: opts.after === undefined ? 120 : opts.after },
    children: (Array.isArray(runs) ? runs : [runs]).map((r) =>
      typeof r === "string" ? new TextRun(r) : new TextRun(r)
    ),
  });

// Continuation text hanging under a lettered item (keeps a-j from restarting).
const sub = (text, opts = {}) =>
  body(text, { indent: opts.indent || 1.25, after: opts.after === undefined ? 120 : opts.after, bold: opts.bold });

const label = (bold, rest) => [{ text: bold, bold: true }, { text: rest }];

// ---- document --------------------------------------------------------------

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: FONT, size: 24 }, // 24 half-points = 12pt
        paragraph: { spacing: { after: 200 } },
      },
    },
    paragraphStyles: [
      {
        id: "Normal (Web)",
        name: "Normal (Web)",
        basedOn: "Normal",
        quickFormat: true,
        run: { font: FONT, size: 24 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "usa-list",
        levels: [
          {
            level: 0,
            format: LevelFormat.DECIMAL,
            text: "%1.",
            alignment: AlignmentType.START,
            style: {
              run: { font: FONT, size: 24, bold: true },
              paragraph: {
                indent: { left: convertInchesToTwip(0.25), hanging: convertInchesToTwip(0.25) },
              },
            },
          },
          {
            level: 1,
            format: LevelFormat.LOWER_LETTER,
            text: "%2.",
            alignment: AlignmentType.START,
            style: {
              run: { font: FONT, size: 24, bold: false },
              paragraph: {
                indent: { left: convertInchesToTwip(0.75), hanging: convertInchesToTwip(0.25) },
              },
            },
          },
        ],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 }, // US Letter
          margin: {
            top: convertInchesToTwip(1),
            bottom: convertInchesToTwip(1),
            left: convertInchesToTwip(1),
            right: convertInchesToTwip(1),
          },
        },
      },
      children: [
        // ---- date -----------------------------------------------------------
        body(`${P} (Date)`, { after: 320 }),

        // ---- addressee ------------------------------------------------------
        body("San Antonio Water System", { after: 0 }),
        body("2800 US Hwy 281 North", { after: 0 }),
        body("San Antonio, Texas 78212", { after: 320 }),

        // ---- RE block -------------------------------------------------------
        new Paragraph({
          style: "Normal (Web)",
          spacing: { after: 0 },
          children: [
            new TextRun({ text: "RE:\t", bold: true }),
            new TextRun({ text: "Utility Service Agreement (USA) Request", bold: true }),
          ],
        }),
        body(`Project Name: ${P}`, { indent: 0.5, after: 0 }),
        body(`Site Address: ${P}, San Antonio, Texas ${P}`, { indent: 0.5, after: 0 }),
        body(`ETJ Status: ${P} (inside City Limits / City of San Antonio ETJ)`, { indent: 0.5, after: 0 }),
        body(`County: ${P} County, Texas`, { indent: 0.5, after: 320 }),

        // ---- salutation / opening ------------------------------------------
        body("To Whom It May Concern:", { after: 200 }),
        body(
          "This letter lists the general requirements necessary to obtain a Utility Service " +
            `Agreement (USA) for water and sanitary sewer service for the above-referenced project, ${P}.`,
          { after: 240 }
        ),

        // ================= 1. ENGINEERING REPORT =============================
        item(0, [{ text: "Engineering Report", bold: true }], { after: 160 }),

        // a. Project Name
        item(1, label("Project Name — ", P)),

        // b. Consulting Engineer
        item(1, [{ text: "Consulting Engineer", bold: true }], { after: 60 }),
        sub(`Firm: ${P}`, { after: 0 }),
        sub(`Address: ${P}`, { after: 0 }),
        sub(`TBPE Firm Registration No.: ${P}`, { after: 0 }),
        sub(`Phone: ${P} (office) / ${P} (direct)`, { after: 0 }),
        sub(`Contact: ${P}, P.E.`, { after: 0 }),
        sub(`Email: ${P}`, { after: 160 }),

        // c. Developer
        item(1, [{ text: "Developer", bold: true }], { after: 60 }),
        sub(`Entity: ${P}`, { after: 0 }),
        sub(`Attn.: ${P}`, { after: 0 }),
        sub(`Address: ${P}`, { after: 160 }),

        // d. Location Map
        item(1, label("Location Map — ", `The site is located within Ferguson Map Grid ${P} (see enclosed Vicinity Exhibit).`)),

        // e. Site Map with Elevation Contours
        item(1, [{ text: "Site Map with Elevation Contours", bold: true }], { after: 60 }),
        sub(`Drainage generally flows to the ${P}.`, { after: 0 }),
        sub(`Average Slope: ±${P}%`, { after: 0 }),
        sub(`Maximum Elevation: ±${P} ft, Minimum Elevation: ±${P} ft`, { after: 0 }),
        sub("(see enclosed Aerial with Contours Exhibit)", { after: 160 }),

        // f. Total Acreage
        item(1, label("Total Acreage — ", `±${P} acres. The tract is currently ${P} (platted / unplatted).`)),

        // g. Projected Flow
        item(1, [{ text: "Projected Flow", bold: true }], { after: 60 }),
        sub(`Existing Water Service: ${P} EDUs`, { after: 0 }),
        sub(`Proposed Water Service: ${P} EDUs`, { after: 0 }),
        sub(`Existing Sanitary Sewer Service: ${P} EDUs`, { after: 0 }),
        sub(`Proposed Sanitary Sewer Service: ${P} EDUs`, { after: 0 }),
        sub("(see enclosed EDU Calculations)", { after: 160 }),

        // h. Fire Flow
        item(1, [{ text: "Statement of Fire Flow Required", bold: true }], { after: 60 }),
        sub(`Residential: ${P} GPM (to be confirmed)`, { after: 0 }),
        sub(`Commercial: ${P} GPM (to be confirmed)`, { after: 160 }),

        // i. Proposed Source of Service
        item(1, [{ text: "Proposed Source of Service", bold: true }], { after: 60 }),
        sub("Water", { indent: 1.25, bold: true, after: 60 }),
        sub(
          `Water service is proposed by connection to an existing ${P}" ${P} water main located within ` +
            `the ${P} right-of-way, constructed under SAWS Job No. ${P}. ${P} (Describe any required bores, ` +
            `crossings, or looping requirements.) Reference SAWS Water Block Map ${P}, which is stamped ` +
            `"${P}." (Please see enclosed SAWS Block Maps)`,
          { after: 160 }
        ),
        sub("Sanitary Sewer", { indent: 1.25, bold: true, after: 60 }),
        sub(
          `Sanitary sewer service is proposed by connection to an existing ${P}" ${P} sanitary sewer main ` +
            `located within the ${P} right-of-way, constructed under SAWS Job No. ${P}. ${P} (Describe any ` +
            `required bores, crossings, or off-site extensions.) Reference SAWS Sewer Block Map ${P}, which ` +
            `is stamped "${P}." (Please see enclosed SAWS Block Maps)`,
          { after: 160 }
        ),

        // j. Linear Feet
        item(1, [{ text: "Total Linear Feet of On-site and Off-site Mains", bold: true }], { after: 60 }),
        sub(`Water: +/-${P} LF of ${P}" ${P} water main (on-site); +/-${P} LF of ${P}" ${P} water main (off-site). [State "None proposed" if none.]`, { after: 0 }),
        sub(`Sanitary Sewer: +/-${P} LF of ${P}" ${P} sanitary sewer main (on-site); +/-${P} LF of ${P}" ${P} sanitary sewer main (off-site). [State "None proposed" if none.]`, { after: 240 }),

        // ================= 2. PROOF OF OWNERSHIP =============================
        item(0, [{ text: "Proof of Ownership", bold: true }], { after: 60 }),
        body(
          `(General Warranty Deed dated ${P}, from ${P}, Grantor, to ${P}, Grantee, recorded as ` +
            `Document No. ${P}, Official Public Records of Bexar County, Texas — see enclosed General ` +
            `Warranty Deed.)`,
          { indent: 0.25, after: 240 }
        ),

        // ================= 3. LEGAL DESCRIPTION ==============================
        item(0, [{ text: "Legal Description of Tract", bold: true }], { after: 60 }),
        body(
          `CB ${P}, ABS ${P}, ±${P} ACRES, ${P}, SAN ANTONIO, TEXAS ${P}; ` +
            `BEXAR CAD PROPERTY ID ${P}, GEOGRAPHIC ID ${P}.`,
          { indent: 0.25, caps: true, after: 120 }
        ),
        body(
          "A metes and bounds description will be provided upon completion of the boundary survey.",
          { indent: 0.25, after: 280 }
        ),

        // ---- closing --------------------------------------------------------
        body(
          `Should you have any questions or require additional information, please contact me directly at ${P}.`,
          { after: 320 }
        ),
        body("Sincerely,", { after: 560 }),
        body(`${P}, P.E.`, { after: 0 }),
        body(`${P} (Title)`, { after: 0 }),
        body(`${P} (Email)`, { after: 320 }),

        // ---- enclosures -----------------------------------------------------
        body("Enclosures:", { bold: true, after: 60 }),
        body("Vicinity Exhibit", { indent: 0.25, after: 0 }),
        body("Aerial with Contours Exhibit", { indent: 0.25, after: 0 }),
        body("EDU Calculations", { indent: 0.25, after: 0 }),
        body("SAWS Block Maps", { indent: 0.25, after: 0 }),
        body("General Warranty Deed", { indent: 0.25, after: 0 }),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(process.argv[2] || "saws-usa-letter.docx", buf);
  console.log("wrote", process.argv[2]);
});
