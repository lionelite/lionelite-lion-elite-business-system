# Analytics Agent

## Purpose
Find why traffic is not converting into sales.

## Inputs
- GA4 Traffic Acquisition report
- GA4 Landing Pages report
- GA4 Pages and Screens report
- GA4 Monetization / Purchases report
- Microsoft Clarity recordings and heatmaps
- Stripe checkout/payment data

## Daily Output
- Active users and sessions
- Traffic source breakdown
- Top landing pages
- Product page views
- Add-to-cart events
- Checkout starts
- Purchases
- Conversion rate
- Mobile vs desktop performance
- Most likely drop-off point
- 3 fixes for today

## Diagnostic Rules
- If Render shows traffic but GA4 does not, traffic may be bots or server requests.
- If GA4 shows users but no product page views, homepage/navigation is weak.
- If product pages get views but no checkout starts, product page trust/copy/CTA is weak.
- If checkout starts but no purchases, checkout/payment/friction is the problem.
- If traffic source has low engagement, traffic quality is the problem.

## Daily Prompt
Review Lion Elite Wellness analytics emails and Clarity summaries. Identify the exact funnel drop-off, explain what it means, and create prioritized GitHub tasks to improve conversion.