const axios = require('axios');

const TSE_HEADERS = {
  'User-Agent': 'Mozilla/5.0',
  'Referer': 'http://www.tsetmc.com/',
};

async function searchInstrument(query) {
  const { data } = await axios.get(
    `https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/${encodeURIComponent(query)}`,
    { headers: TSE_HEADERS, timeout: 7000 }
  );
  return data;
}

async function getClosingPrice(code) {
  const { data } = await axios.get(
    `https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/${code}`,
    { headers: TSE_HEADERS, timeout: 7000 }
  );

  const d = data.closingPriceInfo;

  return {
    code,
    lastPrice: d?.pDrCotVal ?? null,
    closingPrice: d?.pClosing ?? null,
    yesterdayPrice: d?.priceYesterday ?? null,
    change: d?.priceChange ?? null,
    changePercent: d?.priceYesterday
      ? Number((((d.pClosing - d.priceYesterday) / d.priceYesterday) * 100).toFixed(2))
      : null,
  };
}

module.exports = {
  searchInstrument,
  getClosingPrice,
};
