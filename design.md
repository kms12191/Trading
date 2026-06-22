# Stock & Coin Trading Bot Design Guidelines (디자인.md)

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
* **AI Accent (AI Secondary)**: Luminous Cyan (`#00e0ff`) & Indigo Gradient - Used exclusively for AI suggestions, insights, and chatbot assistant components.
* **Semantic Logic**:
  * Bullish / Gains: **Success Green**
  * Bearish / Losses: **Danger Red**
  * *※ Semantic green and red are strictly reserved for financial performance metrics. Do not use them for general UI decorations to avoid false signals.*

### 2.2 Typography
* **UI Labels & Body Text**: **Inter** - For high legibility and neutral UI presentation.
* **Numerical & Code Data**: **JetBrains Mono** - A monospace font used for numerical feeds, ticker symbols, transaction IDs, and amount input fields. This ensures character distinctness (e.g., distinguishing '0' from 'O') and prevents layout jitter during real-time data updates.
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
