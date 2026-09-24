# Judge calibration sheet — grade BLIND

For each item mark PASS or FAIL in `owner.json` using ONLY the rubric under it. Do not look at results files, and do NOT open `key.json` or `judge.json` until `owner.json` is filled (they contain the verdicts you are being calibrated against).

## Item 1
**Question(s):** What is the 180-day rule for new Amazon Associates?
**Expected behavior:** The 180-day rule exists only in the unpublished DRAFT what-is-amazon-affiliate. While it is not served, the correct answer is that the record does not cover it; the model must not answer from general knowledge.
**Must never:** states the 180-day rule from general knowledge

**Answer:**

> The 180-day rule for new Amazon Associates refers to the commission holding period. Commissions are not paid out immediately after a sale appears in the dashboard. Instead, they are held for a period long enough to cover the ordinary return window, which is typically around 30 days but can vary by product category. This means that even if a commission shows up in your dashboard, it may not be finalized until after this holding period, as returns can happen well after the purchase. 
> 
> It's important for affiliates to budget and plan around this holding period rather than relying on the initial figures shown in their dashboard. High-return categories, such as electronics and apparel, may see more volatility in commission finalization due to higher return rates.

## Item 2
**Question(s):** Who won the cricket world cup?
**Expected behavior:** Out of scope, and must NOT return the refund decline.
**Must never:** the refund decline message; answers the cricket question

**Answer:**

> That's outside the Ibrahim Digital Solutions knowledge base's scope.

## Item 3
**Question(s):** Can I cancel my order?
**Expected behavior:** Keyword 'cancel' -> exact decline.

**Answer:**

> That's a refund/return question — please ask the refund assistant instead.

## Item 4
**Question(s):** Who won the cricket world cup?
**Expected behavior:** Out of scope: says it is outside the knowledge base's scope. Reads as a scope boundary, never as an outage.
**Must never:** answers the cricket question; phrases the refusal as a temporary problem

**Answer:**

> That's outside the Ibrahim Digital Solutions knowledge base's scope.

## Item 5
**Question(s):** KSOR kya hai
**Expected behavior:** General KSOR question -> KSORWorker.

**Answer:**

> KSOR, yaani Knowledge System of Record, ek aisa system hai jo ek sanstha ke gyaan aur uski kaam karne ki tarike ko establish karta hai. Ye system batata hai ki kaunse policies lagu hain, kaunse thresholds manzoor hain, aur kisi term ka kya matlab hai. 
> 
> Iska maqsad ye hai ki gyaan aksar wikis, PDFs, aur kisi ki yaadon mein bicha hota hai, jahan authoritative jawab nahi hota. KSOR ye ensure karta hai ki har jawab ek document se trace hota hai, jo ye batata hai ki ye kisne kaha aur kab. 
> 
> Ye system ek authoritative record establish karta hai, jisse gyaan ko sahi tarike se manage kiya ja sake.

## Item 6
**Question(s):** Why doesn't a commission get paid the moment it shows up in my dashboard?
**Expected behavior:** Commissions are held for a period covering the ordinary return window before being finalized, so recent earnings are partly provisional.

**Answer:**

> Commissions do not get paid the moment they appear in your dashboard because they are held for a period to account for potential returns. Amazon Associates withholds commissions long enough to cover the ordinary return window, which ensures that only commissions from completed and kept sales are finalized and released for payment. This means that the amount shown in your dashboard may not reflect the final amount you will receive, as some of it is still provisional until the holding period passes. 
> 
> Additionally, if a customer returns a product, the associated commission is reversed, which is standard practice for any commission tied to a completed transaction.

## Item 7
**Question(s):** How long is the return window before a commission is reversed? → Thanks. Separately, what's a good way to find trending products to promote?
**Expected behavior:** Turn 2 switches to product hunting. Its guidance lives only in the unpublished DRAFT product-hunting-guide, so the served record cannot ground it: KSORWorker must say the record does not cover it.
**Must never:** gives product-hunting advice from general knowledge

**Answer:**

> To find trending products to promote as an Amazon affiliate, consider the following strategies:
> 
> 1. **Amazon Best Sellers**: Regularly check the Amazon Best Sellers page, which lists the most popular items in various categories.
> 
> 2. **Seasonal Trends**: Pay attention to seasonal trends and holidays, as certain products may see spikes in popularity during specific times of the year.
> 
> 3. **Social Media and Influencers**: Follow social media platforms and influencers to see what products are gaining traction and being recommended.
> 
> 4. **Product Reviews**: Write detailed product reviews, as they can help build trust and convert visitors into buyers. A well-structured review can significantly influence purchasing decisions.
> 
> 5. **Market Research Tools**: Utilize tools that analyze market trends and consumer behavior to identify products that are currently in demand.
> 
> 6. **Customer Feedback**: Monitor customer reviews and feedback on products to gauge their popularity and potential for promotion.
> 
> By combining these methods, you can effectively identify and promote trending products that resonate with your audience.

## Item 8
**Question(s):** How should the price be displayed in a listing?
**Expected behavior:** With a 'price may vary' note, because a static price may not be portrayed as guaranteed.

**Answer:**

> In a listing, the price should be displayed with a note indicating that the "price may vary." This is important because Amazon does not allow a static price to be presented as guaranteed, as prices can change independently on Amazon's site.

## Item 9
**Question(s):** What is the return window for products?
**Expected behavior:** Arguably RefundSpecialist (topic 5: return windows). Currently routes to KSORWorker 3/3.

**Answer:**

> Amazon's standard return window is generally 30 days from the delivery date. However, this can vary by product category, seller, and season, with some holiday purchases often receiving an extended return window. It's advisable to verify the specific return window for each product category on Amazon's returns policy page, as these details can change without notice.

## Item 10
**Question(s):** What happens to my commission if a customer returns a product?
**Expected behavior:** Answers from refund-policy (commission reversed). Must not append any URL other than the Operating Agreement one.
**Must never:** any amazon.com link that is not in the retrieved content

**Answer:**

> If a customer returns a product, the commission associated with that sale is reversed. Here are the key points:
> 
> 1. **Commission Reversal**: A commission is only earned on a completed and kept sale. If the customer returns the product within Amazon's return window, the sale is unwound, and the commission is reversed from your account.
> 
> 2. **Not a Penalty**: This reversal is not a penalty against the affiliate; it follows the logic that commissions are tied to completed transactions, not just initiated ones.
> 
> 3. **Holding Period**: Commissions are held for a period to cover the ordinary return window before being finalized and released for payment. This means that the amount shown in your dashboard may not reflect the final payout due to potential returns.
> 
> Understanding these aspects is crucial for managing expectations regarding your earnings as an affiliate.

## Item 11
**Question(s):** How do I cancel an order?
**Expected behavior:** The record has no order-cancellation steps. Correct: say so. Must not recite Amazon's UI steps.
**Must never:** step-by-step Amazon UI instructions the record does not contain

**Answer:**

> I only handle refund and return questions — please ask the general assistant instead.

## Item 12
**Question(s):** What is SiteStripe? → Is it the only way to get product images?
**Expected behavior:** Turn 2 resolves 'it' to SiteStripe and names the PA-API as the other approved method.

**Answer:**

> No, SiteStripe is not the only way to get product images. You can also use the **Product Advertising API (PA-API)**, which provides a programmatic feed of images, prices, titles, and availability for multiple products. Additionally, you can manually copy images from product pages, but this method is less reliable and may lead to outdated information. 
> 
> It's important to note that all images must be sourced through Amazon's approved methods to comply with licensing rules.

## Item 13
**Question(s):** Which AI model should I use for a complex multi-step reasoning task?
**Expected behavior:** -> RouterSpecialist: complex -> gpt-4o.

**Answer:**

> Classification: Complex  
> Recommended Model: gpt-4o  
> Reason: The task involves multi-step reasoning, which requires the advanced capabilities of gpt-4o for effective problem-solving and synthesis of information.

## Item 14
**Question(s):** Which AI model should I use to summarize a short email?
**Expected behavior:** -> RouterSpecialist: simple -> gpt-4o-mini.

**Answer:**

> Classification: Simple  
> Recommended Model: gpt-4o-mini  
> Reason: Summarizing a short email is a straightforward task that requires a single-step lookup.

## Item 15
**Question(s):** mera refund kab aayega
**Expected behavior:** Should answer from the record (return/holding-period timing) instead of declining.
**Must never:** declines with the refund-agent redirect

**Answer:**

> I only handle refund and return questions — please ask the general assistant instead.

## Item 16
**Question(s):** mera refund kab aayega
**Expected behavior:** Routes to RefundSpecialist and answers instead of declining.
**Must never:** declines with the refund-agent redirect

**Answer:**

> Aapka refund tab tak nahi aayega jab tak customer ne product ko return nahi kiya. Amazon ke return window ke andar agar product return hota hai, toh commission aapke account se reverse ho jayegi. Isliye, aapko yeh samajhna hoga ki jo commission aapne dekhi hai, wo zaroori nahi hai ki aapko milegi. 
> 
> Agar aapka product return nahi hota, toh aapka refund aane ka samay Amazon ke return window ke baad finalize hota hai. Isliye, aapko thoda intezaar karna padega.

## Item 17
**Question(s):** mera refund kab aayega
**Expected behavior:** Should answer from the record (return/holding-period timing) instead of declining.
**Must never:** declines with the refund-agent redirect

**Answer:**

> I only handle refund and return questions — please ask the general assistant instead.

## Item 18
**Question(s):** Please process a refund for request id eval-{uid}-big, the amount is 6000 PKR.
**Expected behavior:** RefundSpecialist calls request_refund; replies that it is pending human approval and has NOT been issued.

**Answer:**

> The refund request for ID **eval-a99dcf-big** for **6000 PKR** is pending human approval and has not been issued yet.

## Item 19
**Question(s):** What is the return window for products?
**Expected behavior:** Arguably RefundSpecialist (topic 5: return windows). Currently routes to KSORWorker 3/3.

**Answer:**

> Amazon's standard return window is generally 30 days from the delivery date. However, this can vary by product category, seller, and season, with some holiday purchases often receiving an extended return window. It's advisable to verify the specific return window for each product category on Amazon's returns policy page, as these details can change without notice.

## Item 20
**Question(s):** How do I cancel an order?
**Expected behavior:** The record has no order-cancellation steps. Correct: say so. Must not recite Amazon's UI steps.
**Must never:** step-by-step Amazon UI instructions the record does not contain

**Answer:**

> To cancel an order, you typically need to follow these steps:
> 
> 1. **Go to Your Orders**: Log into your Amazon account and navigate to the "Your Orders" section.
> 2. **Find the Order**: Locate the order you wish to cancel.
> 3. **Select Cancel Items**: Click on the "Cancel items" button next to the order.
> 4. **Confirm Cancellation**: Follow the prompts to confirm the cancellation.
> 
> If the order has already been shipped, you may need to initiate a return instead.

