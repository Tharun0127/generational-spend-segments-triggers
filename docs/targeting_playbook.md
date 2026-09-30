# Targeting playbook

One page: which segment gets which offer, what triggers the contact, and how to know it worked.
Built on synthetic data, so treat it as a test plan, not as proven results.

## Segment plays

| Segment | Offer | Why | Trigger | Success metric |
|---|---|---|---|---|
| **Premium Household Shoppers** | Lead with the annual travel credit (rank 1 of 5, score 0.52) and add the monthly dining credit (rank 1 of 5, score 0.48). | Highest spend per customer ($9,510 a month) with only 1.4% of wallet in travel. | First travel (3 customers fired it in the backtest) and dining cooling (86 customers fired it in the backtest). | Travel and dining spend per customer against holdout. |
| **Big-Ticket Travelers** | Use the travel credit to defend spend, not to grow it (rank 5 of 5, score 0.01 on the growth score because travel is already 20% of wallet). | The only segment where travel is a habit, so a fall in travel is worth a contact. | Travel drop (77 customers fired it in the backtest, $445,595 at stake). | Travel spend in the 3 months after the trigger against holdout. |
| **Digital Shoppers** | Monthly dining credit (rank 2 of 5, score 0.36), delivered in the app. | Most online segment (42% of channel-tagged spend) and the most frequent (108 transactions a month). | Dining cooling (45 customers fired it in the backtest). | Months with a dining transaction and dining spend against holdout. |
| **Mainstream Everyday Spenders** | Annual travel credit as a test cell (rank 2 of 5, score 0.28). No dining credit yet (rank 4 of 5, score 0.29). | Largest segment (48% of customers), so even a small lift adds up, but spend per customer is average. | First travel (15 customers fired it in the backtest). | Share with a travel purchase of $100 or more in the year against holdout. |
| **Light Home and Dining Spenders** | No new credit (rank 5 of 5, score 0.02 for dining, rank 4 of 5, score 0.18 for travel). | Lowest spend ($3,736 a month) and dining already takes 9.5% of it, against 5.2% or less elsewhere, so a credit would mostly pay for existing spend. | Dining cooling as a low-cost retention message (162 customers fired it in the backtest). | Dining transactions in the 3 months after the trigger against holdout. |

## Trigger plays

| Trigger | Rule | Backtest (2019 and 2020) | Offer | Channel | Success metric |
|---|---|---|---|---|---|
| **Travel drop** | Travel spend over the last 3 months is more than 50% below the 3 months before, after allowing for the portfolio-wide change, from a base of at least $200. | 1,029 fires from 647 customers (71% of the base), $2,692,397 at stake. | Bonus points or a statement credit on the next travel booking made within 60 days. | Email plus an in-app message. One contact, then silence for the cooldown period. | Travel spend per customer in the 3 months after the trigger fires. |
| **First travel** | First-ever travel transaction, after at least 3 months on the card with no travel. | 26 fires from 26 customers (3% of the base), $2,147 at stake. | Introduce the annual travel credit and add extra points on travel for 90 days. | App push within two days of the purchase, followed by one email. | Share of customers who make a second travel purchase within 90 days, and travel spend over the same 3 months. |
| **Dining cooling** | Dining transaction count down two months in a row relative to the portfolio, from a base of at least 4 a month, with a total fall of 50% or more. | 1,256 fires from 721 customers (79% of the base), $394,889 at stake. | Reminder of the monthly dining credit, or a one-time dining bonus for customers without it. | App push or email early in the following month, when the monthly credit resets. | Dining transactions and dining spend per customer in the 3 months after the trigger fires. |

## How to measure

- **Design.** Each month, hold back a random 10% of the customers who fire and send them nothing. Compare treated with holdout on the success metric. Never compare before with after, because customers drift back to their usual level on their own.
- **Travel drop.** About 602 fires a year in the backtest, 60 in holdout. At that volume the smallest lift the test can detect is 91%. Detecting a 10% lift needs about 50,047 fires.
- **First travel.** About 26 fires a year in the backtest, 3 in holdout. At that volume the smallest lift the test can detect is 476%. Detecting a 10% lift needs about 58,891 fires.
- **Dining cooling.** About 720 fires a year in the backtest, 72 in holdout. At that volume the smallest lift the test can detect is 22%. Detecting a 10% lift needs about 3,379 fires.
- **Assignment.** Randomize at the customer level the first time a customer fires, and keep the customer in the same arm for later fires. Stratify by segment so both arms have the same mix.
- **Contact rules.** Travel drop and dining cooling fired for the same customer in the same month 64 times in the backtest. When that happens, send the travel offer only, because it has more spend at stake.
- **Read-out.** Report lift as treated minus holdout with a confidence interval, per trigger and per segment. Use pre-trigger spend as a covariate to narrow the interval.

## What to keep in mind

- The segments are not independent of demographics. Birth year, gender and city size predict the segment for 96% of customers. The generator built them that way.
- In this data the drop triggers fire about as often on shuffled months as on real ones (0.96x and 0.96x). The backtest shows volume and mechanics. It does not show that the triggers find customers who are really changing.
- The targeting score ranks segments for growth. Headroom treats a low category share as room to grow. It could equally mean no interest in the category.
- Spend at stake is the gap to an expected level, not money an offer would recover.
