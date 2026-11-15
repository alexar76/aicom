# Request for CoinMarketCap’s API team

Subject: Permission for a CoinMarketCap x402 quote pilot on ModelMarket

Hello CoinMarketCap API team,

We run ModelMarket (`https://modelmarket.dev`), a catalogue where agents discover and invoke paid capabilities. We would like to offer a pilot for the latest Bitcoin and Ethereum quotes using your documented x402 endpoint. ModelMarket would forward the fixed request to CoinMarketCap, pay CoinMarketCap’s current x402 price on Base up to 0.01 USDC per request, and return the two attributed USD quotes and their timestamps to the requesting buyer. We propose one live test first. We do not plan to offer bulk downloads or create a market data feed as part of this pilot.

The pilot request is `GET https://pro-api.coinmarketcap.com/x402/v3/cryptocurrency/quotes/latest?id=1,1027`. Could you confirm whether we may list this route as callable, make the x402 payment on behalf of the buyer, and pass the quotes back to that buyer? If this requires a separate agreement or you prefer to publish a provider listing yourself, please let us know what you would need from us.

Could you also confirm the intended Base USDC recipient for this exact route? The current unpaid challenge reports `0x3C5f3a6cE224BB89D72f5EB4232ecC27F67B3eeA`. We use the recipient you confirm to reject unexpected changes before any payment is signed.
