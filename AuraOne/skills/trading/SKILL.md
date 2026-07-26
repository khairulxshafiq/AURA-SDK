---
name: trading
description: "Panduan analisis saham fundamental, gaya dividen ASB, dan indikator teknikal swing trading untuk Bursa Malaysia & Pasaran Antarabangsa."
---

# Trading & Stock Analysis Skill

Garis panduan komprehensif bagi **TradingSubAgent** dan **Supervisor Orchestrator** dalam menilai saham dan menyusun **Laporan Analisis Trading 8-Bahagian** dalam Bahasa Melayu.

---

## 1. Kriteria Penilaian Fundamental (Gaya Dividen ASB)

Apabila membuat penilaian fundamental berasaskan nisbah kewangan (`get_financial_ratios`):

1. **Dividend Yield (TTM)**:
   - `> 5%`: Sangat Baik (Tinggi & menarik untuk simpanan dividen).
   - `3% - 5%`: Sederhana / Sihat.
   - `< 3%`: Rendah (Berfokus kepada pertumbuhan capital gain, bukan dividen).
2. **ROE (Return on Equity)**:
   - `> 15%`: Cemerlang (Pengurusan menggunakan modal pemegang saham secara sangat efisien).
   - `10% - 15%`: Sederhana.
   - `< 10%`: Lemah.
3. **P/E Ratio (Price-to-Earnings)**:
   - `< 15`: Murah / Terkurang Nilai (Undervalued).
   - `15 - 25`: Wajar (Fair Value).
   - `> 25`: Mahal / Ekspektasi Pertumbuhan Tinggi.
4. **Payout Ratio**:
   - `40% - 70%`: Sangat Sihat (Mampu mengekalkan bayaran dividen sambil mengekalkan tunai perniagaan).
   - `> 80%`: Berisiko tinggi dividen dipotong pada masa hadapan.

---

## 2. Kriteria Indikator Teknikal & Momentum (Swing Trading)

Apabila menilai chart dan indikator teknikal (`get_rsi`, `get_sma`):

1. **Relative Strength Index (RSI-14)**:
   - `<= 30`: **Oversold (Terlebih Jual)** -> Peluang belian *rebound* potensi tinggi.
   - `31 - 69`: **Neutral** -> Pengumpulan / Trend berterusan.
   - `>= 70`: **Overbought (Terlebih Beli)** -> Berhati-hati, potensi amaran penarikan balik harga *(pullback)*.
2. **Simple Moving Average (SMA-50)**:
   - Harga > SMA-50: **Bullish Trend** (Arah aliran menaik aktif).
   - Harga < SMA-50: **Bearish Trend** (Arah aliran menurun aktif).

---

## 3. Format Laporan Analisis Trading 8-Bahagian (Bahasa Melayu)

Setiap laporan analisis carian saham mestilah dibentuk dalam format 8-bahagian yang kemas, profesional, dan sedia dibaca di Telegram:

```markdown
📈 LAPORAN ANALISIS TRADING & PORTFOLIO: [NAMA SYARIKAT / TICKER]

1. 📌 PROFIL SYARIKAT & SEKTOR
   • Nama: [Nama Syarikat] ([Ticker])
   • Sektor / Industri: [Sektor]

2. 📊 PETIKAN HARGA PASARAN LIVE
   • Harga Semasa: RM [Harga] (Julat 52-Minggu: RM [Low] - RM [High])
   • Pemodalan Pasaran (Market Cap): RM [Market Cap]
   • Nisbah P/E: [P/E] | EPS: [EPS]

3. 📈 ANALISIS FUNDAMENTAL (GAYA ASB)
   • Pertumbuhan Hasil & Keuntungan: Revenue Growth [x]%, Earnings Growth [y]%
   • Pulangan atas Ekuiti (ROE): [ROE]% ([Ulasan ROE])
   • Hasil Dividen (Dividend Yield): [DY]% ([Ulasan Dividen])
   • Payout Ratio: [Payout]%

4. 📉 ANALISIS TEKNIKAL & MOMENTUM
   • RSI (14-Hari): [RSI Value] — [Kondisi RSI]
   • Moving Average (SMA-50): RM [SMA-50] — [Status Bullish/Bearish]

5. ⚖️ SKOR STRATEGI PORTFOLIO (/20)
   • Skor Fundamental: [Skor]/10
   • Skor Teknikal: [Skor]/10
   • SKOR KESELURUHAN: [Jumlah]/20

6. 🎯 CADANGAN TRADING SETUP
   • Zon Entry Cadangan: RM [Entry Price Range]
   • Sasaran Keuntungan (TP): RM [Target Price]
   • Hentikan Kerugian (Stop Loss / SL): RM [Stop Loss Price]
   • Nisbah Risk/Reward (R/R): [Ratio]

7. ⚠️ RISIKO UTAMA & AMARAN
   • [Senarai 1-2 risiko fundamental atau volatiliti pasaran]

8. 💡 RUMUSAN PORTFOLIO STRATEGIST
   • [Ulasan penutup ringkas & cadangan jenis portfolio: Core / Satellite / High Risk]
```
