# Stock & Coin Trading Bot Design Guidelines (design.md)

This document is the UI/UX implementation guide based on the **Stock & Coin Trading Bot** project from Stitch MCP. Follow these guidelines strictly for colors, typography, layout, and component design during frontend development.

---

## 1. Brand & Style
* **Concept**: A **Corporate Modern** style that bridges the gap between traditional financial terminal stability and the fluid dynamics of crypto-markets.
* **Digital Layer (AI)**: Elements involving AI-driven chatbot responses and insights must use **Glassmorphism** accents to visually distinguish them as an "intelligent layer" from static data.
* **Visual Direction**: Rooted in deep obsidian navy tones with luminous, high-contrast accent colors to help users make quick, precise trading decisions.

---

## 2. Design Tokens

### 2.1 Colors
* **Background (Level 0)**: Obsidian Navy (`#11131a` or `#0F172A`) - Designed to reduce eye strain during long trading sessions.
* **Cards & Panels (Level 1)**: Slate Navy (`#1E293B`) - Features a 1px solid border (`#334155`) to establish layout hierarchy.
* **Popovers & Modals (Level 2)**: Lighter Navy - Renders with a soft ambient shadow (`0px 8px 24px rgba(0,0,0,0.5)`) for elevated display.
* **Primary Accent (Primary)**: Institutional Blue (`#0047bb`) - Represents institutional trust; used for core brand elements and primary action buttons.
* **Action Blue (Runtime Primary)**: Tailwind `blue-600` / `blue-700` - Used for compact, high-frequency action buttons already implemented in the app, such as header search `이동` and News tab `원문 열기`.
* **AI Accent (AI Secondary)**: Luminous Cyan (`#00e0ff`) & Indigo Gradient - Used exclusively for AI suggestions, insights, and chatbot assistant components.
* **Semantic Logic**:
  * Bullish / Gains: **Success Green**
  * Bearish / Losses: **Danger Red**
  * *Semantic green and red are strictly reserved for financial performance metrics. Do not use them for general UI decorations to avoid false signals.*

### 2.2 Typography
* **UI Labels & Body Text**: **Inter** - For high legibility and neutral UI presentation.
* **Numerical & Code Data**: **JetBrains Mono** - A monospace font used for numerical feeds, ticker symbols, transaction IDs, and amount input fields. This ensures character distinctness and prevents layout jitter during real-time data updates.
* **Hierarchy**: Established through weight and color contrast rather than excessive text sizes.

### 2.3 Layout & Spacing
* **Grid**: 12-column fluid grid for desktop layouts; 4-column grid for mobile screens.
* **Spacing Unit**: Governed by a strict 4px base-unit system (8pt grid).
* **Dashboard Area**: Tight spacing (`8px` to `12px`) to maximize data density and information visible above the fold without scrolling.
* **AI Insight Area**: Loose spacing (`24px`) to provide high readability for long-form analysis.

---

## 3. Core UI Components

### 3.1 Trade Approval Card (Human-in-the-Loop)
This is the highest priority interactive card, rendered only when trade proposals are in `PENDING` status.
* **Design**: Features a 2px left-accent border in `Secondary Cyan (#00e0ff)` to differentiate it from normal text messages.
* **Content Structure**:
  1. A clear **Rationale** section explaining the AI's logic behind the proposal.
  2. Transaction details table: Asset Name, Ticker, Quantity, Estimated Amount, Estimated Fees, and Estimated Cash Ratio Change (before/after simulation).
  3. Action buttons: **[Approve Trade (Success Green)]** and **[Reject (Danger Red)]**.

### 3.2 Input Fields
* **Background**: Obsidian Navy (`#0F172A`) with a 1px Slate border.
* **Focus State**: The border glows with `Primary Blue` on focus.
* **Amount / Quantity Inputs**: Must use JetBrains Mono (monospace) to visualize numerical input with high precision.

### 3.3 Ticker Chips
* **Structure**: Displays the ticker symbol (`JetBrains Mono`) alongside the 24-hour change percentage.
* **Colors**: Uses a subtle 10% opacity background tint (Success Green for gains, Danger Red for losses) to indicate trend direction at a glance.

### 3.4 Header Quick Search
* **Behavior**: Header search is a unified symbol/name search. Do not expose manual `주식 / 코인` filtering controls in the header.
* **Routing**: Search results should rely on backend symbol metadata (`asset_type`) to route users to the correct stock or crypto detail page.
* **Input Style**: Use the standard input token: Obsidian Navy background (`#0F172A`), Slate border, `JetBrains Mono`, compact height, and blue focus border.
* **Primary Search Action**: The `이동` button uses the compact runtime primary action style: `bg-blue-600`, `hover:bg-blue-700`, white text, bold label, and `active:scale-95`.

### 3.5 News Board Actions
* **Card Context**: News cards use Slate panels with subtle cyan hover borders. Category/source chips may use cyan borders as metadata accents.
* **Summary Action**: Secondary actions such as `요약 보기` should remain Slate border buttons to avoid competing with the main external-link action.
* **Original Article Action**: The `원문 열기` button in the News tab must match the header quick-search `이동` button color treatment: `bg-blue-600`, `hover:bg-blue-700`, white text, bold label, and `active:scale-95`.
* **Scope Rule**: This News Board rule applies to `frontend/src/pages/News.jsx`. Asset detail news components may keep their own local treatment unless explicitly updated.
