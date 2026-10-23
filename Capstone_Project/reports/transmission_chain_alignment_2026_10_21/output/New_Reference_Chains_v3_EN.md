# New Reference Chains and Monitoring Indicators

October 21, 2026 v3: 31 additions, all untested; monitoring suggestions do not establish data availability.

## FICC

### FICC-MBSD-02

Mortgage-backed pool supply or reference data breaks down (for example pool allocation or data errors around month-end settlement) Members cannot satisfy their Pool Deliver Obligations on time, so deliveries fail and the Corporation applies the fails charge to the funds amount of each failed position

Process: MBSD pool settlement and fails charge

Optional monitoring: SIFMA monthly settlement cycle; share of Pool Deliver Obligations failing

### FICC-MBSD-03

A clearing member comes under financial stress (a downgrade, adverse news, or weaker results) The member is placed on the Watch List, so the Corporation can require a Clearing Fund deposit above the Rule 4 amount and the member must meet every margin call regardless of size

Process: MBSD Watch List surveillance and Clearing Fund requirements

Optional monitoring: Member credit rating and outlook; adverse news on a named member

### FICC-GSD-05

Collateral and funding markets tighten during the day (tri-party or general-collateral stress) A netting member cannot meet its GCF Repo Collateral Allocation Obligation or cash obligation by the scheduled deadline, so it is deemed to fail on its net position and owes late fees and interest

Process: GSD GCF Repo collateral allocation and funds settlement

Optional monitoring: SOFR and general-collateral repo rates; GCF Repo late-fee deadlines

### FICC-GSD-07

Cash investors (money market funds, corporates) pull back from repo CCIT tri-party volume and the netting-member counterparties facing those cash lenders contract, shifting funding into or out of the GCF Repo service

Process: GSD CCIT tri-party service and GCF Repo

Optional monitoring: Money market fund repo allocations; tri-party repo volumes (OFR)

### FICC-MBSD-04

Market-wide disruption (exchange trading halt, banking moratorium, or declared emergency) The Corporation invokes its market-disruption / force-majeure powers to suspend, extend, or modify settlement timeframes and obligations

Process: MBSD settlement timeframes under market disruption

Optional monitoring: Exchange halt or trading-moratorium declarations; emergency orders

### FICC-MBSD-05

A cyber event or major outage hits a large member’s systems The member’s connectivity to DTCC systems is impaired, so its submissions and deliveries are disrupted and the Corporation can act under the participant-system-disruption rule

Process: MBSD participant system disruption

Optional monitoring: Sector cyber advisories (CISA); member outage disclosures

### FICC-GSD-09

A sharp move hits futures markets alongside Treasuries Under a cross-margining arrangement, offsetting positions at the linked futures clearing organization change the member’s net risk, so GSD Required Fund Deposit moves with the combined book

Process: GSD cross-margining and Required Fund Deposit

Optional monitoring: Treasury-futures volatility; CME-FICC cross-margin program notices

### FICC-GSD-10

A Treasury auction cycle is heavy or an auction settles poorly Netting-eligible auction purchases flow into netting and must settle on the issue date, concentrating delivery and funding obligations on that day

Process: GSD netting and settlement of auction purchases

Optional monitoring: Treasury auction calendar and sizes; auction tail / bid-to-cover

### FICC-MBSD-06

A large forward pipeline builds (heavy TBA origination into future months) Forward net settlement positions accumulate and are margined until they settle, so a later rate move can swing margin and settlement on a large forward book

Process: MBSD TBA netting and forward settlement positions

Optional monitoring: TBA issuance / forward pipeline; mortgage origination volume

### FICC-MBSD-07

A rate move around options expiry makes many MBS options go in or out of the money On expiration or exercise, members must submit cancellations and resulting trades, and open option contracts keep drawing Required Fund Deposits until settled

Process: MBSD options expiration and exercise

Optional monitoring: MBS options open interest and expiry calendar; rate moves near expiry

### FICC-MBSD-08

Pool-allocation details are sent late or with errors through the pool-notification messaging service EPN messages miss good-delivery (T2) time stamps or carry inaccurate pool data, so counterparties cannot confirm allocations in time and downstream pool settlement is disrupted

Process: MBSD Electronic Pool Notification (EPN) messaging and good delivery

Optional monitoring: EPN message volumes near SIFMA notification cut-offs; reported message errors or discrepancies

### FICC-MBSD-09

A cyber threat targets the pool-notification messaging rail or its users EPN users must maintain a cybersecurity program and confirmation; a cyber event can impair message submission or receipt and the Corporation can decline to act on non-conforming messages

Process: MBSD EPN cybersecurity and message eligibility

Optional monitoring: Financial-sector cyber advisories (CISA / FS-ISAC); EPN user outage or breach disclosures

### FICC-GSD-11

A buy-side executing-firm customer (for example a hedge fund) comes under stress or fails The Agent Clearing Member that submitted the customer’s trades remains responsible to the Corporation for them, so the stress is concentrated on that agent member

Process: GSD Agent Clearing Service

Optional monitoring: Hedge-fund / leveraged-investor stress; agent-cleared Treasury volumes

## ECS

### ECS-NSCC-04

Large concentrated positions at a member Member capital or liquidity is strained

Process: NSCC raises that member's requirements

Optional monitoring: Not specified in the reference.

### ECS-NSCC-05

A large intraday payment or liquidity stress hits the equity market The Corporation’s daily liquidity need rises, so it can call Supplemental Liquidity Deposits from members (and affiliated families) with the largest liquidity exposure

Process: NSCC supplemental liquidity deposits

Optional monitoring: Equity market volatility near expiry/roll dates; large single-member liquidity exposure

### ECS-NSCC-07

A settling bank has an operational or credit problem The settling bank refuses or fails to settle a member’s net-net balance over Fedwire, so NSCC money settlement for that member cannot complete on time

Process: NSCC settling-bank money settlement

Optional monitoring: Settling-bank credit or outage news; Fedwire disruption notices

### ECS-NSCC-08

A retail broker fails or exits abruptly A wave of customer accounts is moved through the Automated Customer Account Transfer Service (ACATS) within fixed timeframes, concentrating transfer and settlement activity

Process: NSCC ACATS customer account transfers

Optional monitoring: Broker failures / FINRA actions; ACATS transfer volumes

### ECS-NSCC-09

Securities-financing (repo / stock-loan) markets come under stress Novated Securities Financing Transactions in the SFT clearing service reprice and remargin, so member collateral and settlement obligations on the SFT book move sharply

Process: NSCC Securities Financing Transaction clearing service

Optional monitoring: Repo / securities-lending spreads; SFT cleared volumes

### ECS-DTC-01

A money-market issuer or its issuing/paying agent has a funding problem The issuing and paying agent cannot give the MMI funding acknowledgment for the day’s presentments, so MMI maturity and issuance settlement for that acronym stalls

Process: DTC MMI settlement (funding acknowledgment)

Optional monitoring: Short-term funding stress (CP / MMI); issuer or IPA credit news

### ECS-DTC-03

Market-wide disruption (exchange halt, banking moratorium, or declared emergency) The Corporation invokes its market-disruption / force-majeure powers to suspend, extend, or modify DTC settlement obligations and timeframes

Process: DTC settlement timeframes under market disruption

Optional monitoring: Exchange halt or trading-moratorium declarations; emergency orders

### ECS-NSCC-10

Physical processing or back-office operations are disrupted (for example a site event) Envelope Settlement Service deliveries, money-only charges, and dividend/interest claims back up, delaying associated money settlement

Process: NSCC Envelope Settlement Service

Optional monitoring: Operations-site disruption notices; ESS envelope / claim volumes

### ECS-DTC-04

A disruption hits the Canadian market or the CDS link Canadian-Link cross-border transactions through the DTC-CDS interface cannot settle normally, so cross-border delivery and settlement stall

Process: DTC Canadian-Link cross-border settlement

Optional monitoring: Canadian market stress; CDS link status / cross-border volumes

### ECS-DTC-06

A sharp intraday price move or a participant liquidity squeeze A receiving participant’s intraday net debit approaches its Net Debit Cap or its Collateral Monitor turns insufficient, so DTC blocks the DVP book-entry delivery until collateral or funding is restored

Process: DTC risk management controls (Net Debit Cap and Collateral Monitor)

Optional monitoring: Intraday equity/fixed-income volatility; participant funding stress

### ECS-NSCC-12

A foreign financial institution linked to NSCC comes under stress or its market is disrupted Cross-border link transactions between that foreign institution’s participants and NSCC Members cannot clear or settle normally under the International Links arrangement

Process: NSCC International Links

Optional monitoring: Foreign-market or foreign-FI stress; cross-border link transaction volumes

## Asset Services

### AssetSvc-DTC-01

A regulator halts or suspends trading in a security, or fraud is identified The Corporation imposes a Deposit Chill or Global Lock, restricting deposits or book-entry services for that security across all participants

Process: DTC deposit chills and global locks

Optional monitoring: FINRA trading halts / SEC trading suspensions; court orders on a security

### AssetSvc-DTC-02

An issuer or transfer agent has transfer or registration problems The Corporation may decline to credit deposits of that issue until registration into its nominee is confirmed, so custody and asset-servicing of the affected security are disrupted

Process: DTC custody / deposit and transfer services

Optional monitoring: Transfer-agent problems; issuer registration or re-org events

### AssetSvc-DTC-03

A derivatives clearing organization or futures broker comes under stress Instructions on swap-margin segregated accounts (pledgee / pledgor access) are disrupted, affecting the collateral held in those segregated accounts

Process: DTC segregated accounts for swap margin

Optional monitoring: Futures / swaps CCP or FCM stress; segregated swap-margin balances

### AssetSvc-DTC-04

A futures commission merchant that holds customer property fails or is stressed Customer-property segregated accounts held under CFTC segregation rules must be moved or protected, concentrating activity on that custody flow

Process: DTC segregated accounts for customer property

Optional monitoring: FCM failures / CFTC actions; customer-property segregated balances

## WIS

### WIS-NSCC-01

An insurance carrier or retirement-services member comes under stress Insurance & Retirement Solutions (I&RS) data and the related I&RS payments between members are disrupted, affecting that settlement flow for annuities, life insurance and retirement products

Process: NSCC Insurance & Retirement Solutions settlement

Optional monitoring: Insurer credit stress; I&RS payment volumes

### WIS-NSCC-02

A stress or run hits mutual funds (large redemptions, a pricing or NAV problem) Fund/SERV purchase and redemption orders and the associated money settlement between funds and distributors spike or break, straining that automated settlement flow

Process: NSCC Fund/SERV mutual fund order and settlement

Optional monitoring: Mutual fund flows / large redemptions; Fund/SERV order and settlement volumes

### WIS-NSCC-03

Private-markets / alternative investments come under stress (valuation, liquidity or a fund-administrator problem) Alternative Investment Product (AIP) data and AIP payments between members are disrupted, affecting that private-markets settlement and reporting flow

Process: NSCC Alternative Investment Product (AIP) service

Optional monitoring: Private-markets / alternatives stress; AIP data and payment volumes
