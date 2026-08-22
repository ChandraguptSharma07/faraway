import re

with open('frontend/src/components/CredibilityView.jsx', 'r') as f:
    content = f.read()

content = content.replace("const [shadow, setShadow] = useState(null)", "const [shadow, setShadow] = useState(null)\n  const [modalShadow, setModalShadow] = useState(null)")

fetch_shadow = """
    const pollShadow = () => Promise.all([
      fetchShadowValidation(),
      fetch('/api/modal-calibration').then(r => r.json())
    ])
      .then(([data, modalData]) => {
        if (!active) return
        setShadow(data)
        setModalShadow(modalData)
        const warming = Object.values(data.scenarios).some((row) => row.status === 'WARMING_UP') ||
                        Object.values(modalData.scenarios).some((row) => row.status === 'WARMING_UP')
        if (warming) timer = window.setTimeout(pollShadow, 1500)
      })
"""

# Replace the existing pollShadow definition
content = re.sub(r'const pollShadow = \(\) => fetchShadowValidation\(\).*?\.catch\(\(e\) => \{ if \(active\) setErr\(String\(e\)\) \}\)', fetch_shadow.strip() + '\n      .catch((e) => { if (active) setErr(String(e)) })', content, flags=re.DOTALL)

modal_section = """
          <section className="cred-shadow">
            <h3>LIVE MODAL MODEL · SHADOW VALIDATION</h3>
            <p className="shadow-note">
              Calibrating the live 36-mode catenary vs the implicit distributed reference.
            </p>
            {modalShadow ? (
              <div className="shadow-grid">
                {['250', '300'].map((speed) => (
                  <ShadowCard key={speed} report={modalShadow.scenarios[speed]} col1="LIVE (36-MODE)" />
                ))}
              </div>
            ) : <Loading />}
          </section>

"""

content = content.replace('<section className="cred-shadow">', modal_section + '          <section className="cred-shadow">')

content = content.replace("function ShadowCard({ report }) {", "function ShadowCard({ report, col1 }) {")
content = content.replace("<span role=\"columnheader\">REDUCED</span>", "<span role=\"columnheader\">{col1 || 'REDUCED'}</span>")

with open('frontend/src/components/CredibilityView.jsx', 'w') as f:
    f.write(content)

