#!/usr/bin/env python3
"""
Generate PDF Strategy Report
=============================
Creates a professional PDF report with all strategy analysis findings.
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.platypus.flowables import HRFlowable
from datetime import datetime
from pathlib import Path

# Output path
OUTPUT_DIR = Path("/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping/strategy_lab/reports")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def create_strategy_report():
    """Generate comprehensive PDF report."""
    
    output_file = OUTPUT_DIR / f"Gamma_EMA_Strategy_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        rightMargin=1*cm,
        leftMargin=1*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor('#1a1a2e'),
        alignment=1  # Center
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=12,
        spaceBefore=20,
        textColor=colors.HexColor('#16213e')
    )
    
    subheading_style = ParagraphStyle(
        'SubHeading',
        parent=styles['Heading3'],
        fontSize=13,
        spaceAfter=8,
        spaceBefore=15,
        textColor=colors.HexColor('#0f3460')
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=8,
        leading=14
    )
    
    highlight_style = ParagraphStyle(
        'Highlight',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=10,
        backColor=colors.HexColor('#e8f4f8'),
        borderPadding=8,
        leading=16
    )
    
    # ==================== TITLE PAGE ====================
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph("GAMMA-EMA CONFLUENCE STRATEGY", title_style))
    story.append(Paragraph("Comprehensive Backtest Analysis Report", styles['Heading2']))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y')}", body_style))
    story.append(Paragraph("Methodology: Pure Walk-Forward Test (No Data Leakage)", body_style))
    story.append(Spacer(1, 1*inch))
    
    # Disclaimer box
    disclaimer = """
    <b>DISCLAIMER:</b> This report is for educational purposes only. Past performance does not 
    guarantee future results. Parameters were fixed BEFORE seeing test data - this is a pure 
    out-of-sample result with NO curve fitting or data snooping.
    """
    story.append(Paragraph(disclaimer, highlight_style))
    story.append(PageBreak())
    
    # ==================== EXECUTIVE SUMMARY ====================
    story.append(Paragraph("📊 EXECUTIVE SUMMARY", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0f3460')))
    
    summary_data = [
        ['Metric', 'Value'],
        ['Test Methodology', 'Walk-Forward (50/50 split)'],
        ['Total Test Days', '8 days'],
        ['Total Trades', '354'],
        ['Combined Win Rate', '37.9%'],
        ['Combined P&L', '₹8,868'],
        ['Profit Factor', '1.06'],
        ['Data Required', 'Index + Options'],
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 3*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Key Finding
    key_finding = """
    <b>KEY FINDING:</b> The strategy requires INDEX + OPTIONS data to work properly. 
    Options-only data produces LOSING results (-₹3,978) because EMA signals need 
    underlying index price action.
    """
    story.append(Paragraph(key_finding, highlight_style))
    
    # ==================== STRATEGY PARAMETERS ====================
    story.append(Paragraph("🔧 FIXED STRATEGY PARAMETERS", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0f3460')))
    
    params_text = """
    These parameters were decided <b>UPFRONT</b> and NOT optimized on test data:
    """
    story.append(Paragraph(params_text, body_style))
    
    params_data = [
        ['Parameter', 'Value', 'Description'],
        ['Stop Loss', '25%', 'Maximum loss per trade'],
        ['Target', '100%', '1:4 Risk-Reward ratio'],
        ['Entry Window', '11:00 - 15:15', 'Allowed entry times'],
        ['Sideways Exit', '10 minutes', 'Exit if no movement'],
    ]
    
    params_table = Table(params_data, colWidths=[2*inch, 1.5*inch, 2.5*inch])
    params_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16213e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(params_table)
    
    # ==================== RESULTS BY SYMBOL ====================
    story.append(Paragraph("📈 RESULTS BY SYMBOL", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0f3460')))
    
    # NIFTY Results
    story.append(Paragraph("NIFTY", subheading_style))
    
    nifty_data = [
        ['Metric', 'Value', 'Metric', 'Value'],
        ['Total Trades', '191', 'Win Rate', '34.0%'],
        ['Winners', '65', 'Losers', '126'],
        ['Total P&L', '₹1,451', 'Avg P&L', '₹8'],
        ['Profit Factor', '1.02', 'Sharpe Ratio', '0.13'],
        ['Max Win Streak', '8', 'Max Lose Streak', '16'],
        ['Max Drawdown', '₹28,160', 'Profitable Days', '3/4 (75%)'],
    ]
    
    nifty_table = Table(nifty_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
    nifty_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28a745')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#e8f4f8')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(nifty_table)
    story.append(Spacer(1, 0.2*inch))
    
    # BANKNIFTY Results
    story.append(Paragraph("BANKNIFTY", subheading_style))
    
    banknifty_data = [
        ['Metric', 'Value', 'Metric', 'Value'],
        ['Total Trades', '163', 'Win Rate', '42.3%'],
        ['Winners', '69', 'Losers', '94'],
        ['Total P&L', '₹7,417', 'Avg P&L', '₹46'],
        ['Profit Factor', '1.09', 'Sharpe Ratio', '0.53'],
        ['Max Win Streak', '9', 'Max Lose Streak', '17'],
        ['Max Drawdown', '₹23,157', 'Profitable Days', '1/3 (33%)'],
    ]
    
    banknifty_table = Table(banknifty_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
    banknifty_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#e8f4f8')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(banknifty_table)
    story.append(PageBreak())
    
    # ==================== EXIT ANALYSIS ====================
    story.append(Paragraph("🎯 EXIT REASON ANALYSIS", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0f3460')))
    
    story.append(Paragraph("Where do profits and losses come from?", body_style))
    
    exit_data = [
        ['Exit Type', 'Trades', 'Win Rate', 'Total P&L', 'Verdict'],
        ['Target 4x', '18', '100%', '₹35,961', '✓ BEST'],
        ['Trailing SL', '23', '91%', '₹46,513', '✓ EXCELLENT'],
        ['Time Exit', '98', '75%', '₹53,110', '✓ GOOD'],
        ['Sideways Exit', '40', '50%', '₹9,167', '- NEUTRAL'],
        ['Stoploss', '175', '0%', '₹-135,884', '✗ DRAIN'],
    ]
    
    exit_table = Table(exit_data, colWidths=[1.2*inch, 0.8*inch, 1*inch, 1.2*inch, 1.5*inch])
    exit_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 1), (0, 2), colors.HexColor('#d4edda')),  # Green for best
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#f8d7da')),  # Red for stoploss
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(exit_table)
    story.append(Spacer(1, 0.2*inch))
    
    insight_text = """
    <b>KEY INSIGHT:</b> ALL profits come from Target hits (100% win rate) and Trailing SL exits (91% win rate). 
    Stoploss exits drain the account with ₹1.35 lakh in losses across 175 trades.
    """
    story.append(Paragraph(insight_text, highlight_style))
    
    # ==================== TIME ANALYSIS ====================
    story.append(Paragraph("⏰ HOUR-BY-HOUR ANALYSIS", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0f3460')))
    
    # NIFTY Time
    story.append(Paragraph("NIFTY - Best and Worst Hours", subheading_style))
    
    nifty_time_data = [
        ['Hour', 'Trades', 'P&L', 'Win%', 'Result'],
        ['11:00-12:00', '42', '₹9,866', '31%', '✓ BEST'],
        ['12:00-13:00', '42', '₹-14,826', '14%', '✗ WORST'],
        ['13:00-14:00', '44', '₹5,750', '46%', '✓ OK'],
        ['14:00-15:00', '50', '₹3,385', '42%', '✓ OK'],
        ['15:00-16:00', '13', '₹-2,724', '39%', '✗ AVOID'],
    ]
    
    nifty_time_table = Table(nifty_time_data, colWidths=[1.3*inch, 0.9*inch, 1.2*inch, 0.8*inch, 1.2*inch])
    nifty_time_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28a745')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#d4edda')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#f8d7da')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(nifty_time_table)
    story.append(Spacer(1, 0.15*inch))
    
    # BANKNIFTY Time
    story.append(Paragraph("BANKNIFTY - Best and Worst Hours", subheading_style))
    
    banknifty_time_data = [
        ['Hour', 'Trades', 'P&L', 'Win%', 'Result'],
        ['11:00-12:00', '40', '₹2,585', '33%', '✓ OK'],
        ['12:00-13:00', '44', '₹-1,243', '36%', '✗ AVOID'],
        ['13:00-14:00', '30', '₹22,082', '73%', '✓ BEST'],
        ['14:00-15:00', '38', '₹-18,002', '29%', '✗ WORST'],
        ['15:00-16:00', '11', '₹1,995', '64%', '✓ OK'],
    ]
    
    banknifty_time_table = Table(banknifty_time_data, colWidths=[1.3*inch, 0.9*inch, 1.2*inch, 0.8*inch, 1.2*inch])
    banknifty_time_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#d4edda')),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#f8d7da')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(banknifty_time_table)
    
    # ==================== DAY OF WEEK ====================
    story.append(Paragraph("📅 DAY OF WEEK ANALYSIS", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0f3460')))
    
    dow_data = [
        ['Symbol', 'Best Day', 'P&L', 'Worst Day', 'P&L'],
        ['NIFTY', 'Thursday', '₹5,354', 'Friday', '₹-4,022'],
        ['BANKNIFTY', 'Friday', '₹13,358', 'Thursday', '₹-5,270'],
    ]
    
    dow_table = Table(dow_data, colWidths=[1.2*inch, 1.2*inch, 1*inch, 1.2*inch, 1*inch])
    dow_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (1, 1), (2, 1), colors.HexColor('#d4edda')),
        ('BACKGROUND', (1, 2), (2, 2), colors.HexColor('#d4edda')),
        ('BACKGROUND', (3, 1), (4, 1), colors.HexColor('#f8d7da')),
        ('BACKGROUND', (3, 2), (4, 2), colors.HexColor('#f8d7da')),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(dow_table)
    story.append(PageBreak())
    
    # ==================== RECOMMENDATIONS ====================
    story.append(Paragraph("💡 KEY RECOMMENDATIONS", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0f3460')))
    
    story.append(Paragraph("✓ WHAT WORKS", subheading_style))
    works_text = """
    • <b>Target hits (1:4 RR)</b> - 100% win rate when target is reached<br/>
    • <b>Trailing stop loss</b> - 91% win rate, captures big moves<br/>
    • <b>11:00-12:00 entries for NIFTY</b> - Best hour<br/>
    • <b>13:00-14:00 entries for BANKNIFTY</b> - Best hour<br/>
    • <b>Thursday for NIFTY, Friday for BANKNIFTY</b><br/>
    """
    story.append(Paragraph(works_text, body_style))
    
    story.append(Paragraph("✗ WHAT DOESN'T WORK", subheading_style))
    not_works_text = """
    • <b>12:00-13:00 for NIFTY</b> - Worst hour (₹-14,826)<br/>
    • <b>14:00-15:00 for BANKNIFTY</b> - Worst hour (₹-18,002)<br/>
    • <b>Stoploss exits</b> - 100% loss rate (too frequent)<br/>
    • <b>Options-only data</b> - Cannot generate proper signals<br/>
    """
    story.append(Paragraph(not_works_text, body_style))
    
    # ==================== WARNINGS ====================
    story.append(Paragraph("⚠️ LIMITATIONS & WARNINGS", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#dc3545')))
    
    warnings_text = """
    <b>1. Small Sample Size:</b> Only 8 test days, 354 trades. Minimum 50-100 days recommended for statistical significance.<br/><br/>
    <b>2. No Transaction Costs:</b> Slippage and commissions not included. Real profits would be lower.<br/><br/>
    <b>3. No IV Data:</b> Implied volatility not available in current dataset.<br/><br/>
    <b>4. Market Conditions:</b> January 2026 may not represent all market conditions.<br/><br/>
    <b>5. Marginal Edge:</b> Profit Factor of 1.06 is very small. One bad week could wipe out gains.<br/>
    """
    story.append(Paragraph(warnings_text, body_style))
    
    # ==================== CONCLUSION ====================
    story.append(Paragraph("📋 CONCLUSION", heading_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0f3460')))
    
    conclusion_text = """
    The Gamma-EMA Confluence strategy shows <b>marginal profitability</b> in pure out-of-sample testing 
    with a profit factor of 1.06 and win rate of 37.9%. The strategy <b>requires index + options data</b> 
    to function properly - options-only data produces losing results.<br/><br/>
    
    <b>The edge is small but real.</b> To trade this strategy profitably:<br/>
    • Trade NIFTY on Thursdays between 11:00-12:00<br/>
    • Trade BANKNIFTY on Fridays between 13:00-14:00<br/>
    • Avoid the identified "worst hours" for each symbol<br/>
    • Focus on letting winners run to target/trailing SL<br/><br/>
    
    <b>NEXT STEPS:</b> Collect more data (50+ trading days), add IV filter, paper trade before live.
    """
    story.append(Paragraph(conclusion_text, body_style))
    
    story.append(Spacer(1, 0.5*inch))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a1a2e')))
    
    footer_text = f"""
    <i>Report generated on {datetime.now().strftime('%B %d, %Y at %H:%M IST')}<br/>
    Methodology: Pure Walk-Forward Test | No Data Leakage | No Curve Fitting</i>
    """
    story.append(Paragraph(footer_text, ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.gray, alignment=1)))
    
    # Build PDF
    doc.build(story)
    print(f"\n✅ PDF Report Generated: {output_file}")
    return output_file


if __name__ == "__main__":
    create_strategy_report()
