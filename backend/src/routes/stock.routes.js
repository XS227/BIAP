const express = require('express');
const axios = require('axios');
const router = express.Router();

const TSE_HEADERS = {
  'User-Agent': 'Mozilla/5.0',
  'Referer': 'http://www.tsetmc.com/',
};

const DEFAULT_SYMBOLS = [
  { code: '46348559193224090', name: 'فولاد' },
  { code: '35700344742885862', name: 'خودرو' },
  { code: '778253364357513', name: 'شپنا' },
];

async function fetchOne(sym) {
  try {
    const { data } = await axios.get(
      `https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/${sym.code}`,
      { headers: TSE_HEADERS, timeout: 5000 }
    );
    const d = data.closingPriceInfo;
    return {
      name: sym.name,
      code: sym.code,
      lastPrice: d.pDrCotVal,
      closingPrice: d.pClosing,
      yesterdayPrice: d.priceYesterday,
      change: d.priceChange,
      changePercent: d.priceYesterday
        ? (((d.pClosing - d.priceYesterday) / d.priceYesterday) * 100).toFixed(2)
        : 0,
    };
  } catch (e) {
    return { name: sym.name, code: sym.code, error: true };
  }
}

router.get('/watchlist', async (req, res, next) => {
  try {
    const results = await Promise.all(DEFAULT_SYMBOLS.map(fetchOne));
    res.json({ symbols: results });
  } catch (err) {
    next(err);
  }
});

router.get('/search/:query', async (req, res, next) => {
  try {
    const { data } = await axios.get(
      `https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/${encodeURIComponent(req.params.query)}`,
      { headers: TSE_HEADERS, timeout: 5000 }
    );
    res.json(data);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
