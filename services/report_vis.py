# services/report_visualizations.py - CHART GENERATION

"""
Generate visualizations for credit reports
Charts are saved as PNG and embedded in DOCX
"""

import os
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime


# Set style
plt.style.use('seaborn-v0_8-darkgrid')
COLORS = {
    'primary': '#1E3A8A',    # Navy
    'success': '#16A34A',    # Green
    'warning': '#F59E0B',    # Amber
    'danger': '#DC2626',     # Red
    'info': '#3B82F6',       # Blue
    'teal': '#14B8A6',
}


def create_financial_summary_chart(financial_data: Dict, output_path: str) -> str:
    """
    Create bar chart showing key financial metrics.

    Args:
        financial_data: Dict with chiffre_affaires, resultat_net, capitaux_propres, etc.
        output_path: Where to save the PNG

    Returns:
        Path to saved PNG
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Extract values (in millions for readability)
    metrics = {
        'Chiffre d\'affaires': financial_data.get('chiffre_affaires', 0) / 1_000_000,
        'Résultat net': financial_data.get('resultat_net', 0) / 1_000_000,
        'Capitaux propres': financial_data.get('capitaux_propres', 0) / 1_000_000,
        'Trésorerie': financial_data.get('tresorerie_finale', 0) / 1_000_000,
    }

    # Filter out zeros
    metrics = {k: v for k, v in metrics.items() if v != 0}

    if not metrics:
        # Create empty chart with message
        ax.text(0.5, 0.5, 'Données financières non disponibles',
                ha='center', va='center', fontsize=14, color='gray')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
    else:
        # Create bar chart
        x = np.arange(len(metrics))
        values = list(metrics.values())
        labels = list(metrics.keys())

        # Color bars (green for positive, red for negative)
        colors = [COLORS['success'] if v > 0 else COLORS['danger'] for v in values]

        bars = ax.bar(x, values, color=colors, alpha=0.7, edgecolor='black', linewidth=1.5)

        # Add value labels on bars
        for i, (bar, val) in enumerate(zip(bars, values)):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{val:.1f}M',
                   ha='center', va='bottom' if val > 0 else 'top',
                   fontsize=10, fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=15, ha='right')
        ax.set_ylabel('Montant (Millions DT)', fontsize=11, fontweight='bold')
        ax.set_title('Indicateurs Financiers Clés', fontsize=14, fontweight='bold', pad=20)
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    return output_path


def create_benchmark_comparison_chart(
    company_value: float,
    sector_median: float,
    metric_name: str,
    output_path: str
) -> str:
    """
    Create comparison chart: Company vs Sector Median.
    """
    fig, ax = plt.subplots(figsize=(8, 6))

    categories = ['Entreprise', 'Médiane secteur']
    values = [company_value, sector_median]
    x = np.arange(len(categories))

    # Color based on position
    colors = [COLORS['primary'], COLORS['info']]
    if company_value > sector_median:
        colors[0] = COLORS['success']
    elif company_value < sector_median * 0.7:
        colors[0] = COLORS['warning']

    bars = ax.bar(x, values, color=colors, alpha=0.7, edgecolor='black', linewidth=1.5, width=0.6)

    # Add value labels
    for bar, val in zip(bars, values):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{val:,.0f}',
               ha='center', va='bottom',
               fontsize=11, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=11)
    ax.set_ylabel('Valeur', fontsize=11, fontweight='bold')
    ax.set_title(f'Benchmark: {metric_name}', fontsize=14, fontweight='bold', pad=20)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    return output_path


def create_risk_severity_pie(risks_data: List[Dict], output_path: str) -> str:
    """
    Create pie chart showing risk distribution by severity.
    """
    fig, ax = plt.subplots(figsize=(8, 8))

    # Count risks by severity
    severity_counts = {'Élevé': 0, 'Modéré': 0, 'Faible': 0}

    for risk in risks_data:
        sev = risk.get('severite') or risk.get('Severite', 'Modéré')
        if sev in severity_counts:
            severity_counts[sev] += 1

    # Filter out zeros
    severity_counts = {k: v for k, v in severity_counts.items() if v > 0}

    if not severity_counts:
        ax.text(0.5, 0.5, 'Aucun risque identifié',
                ha='center', va='center', fontsize=14, color='gray')
        ax.axis('off')
    else:
        labels = list(severity_counts.keys())
        sizes = list(severity_counts.values())
        colors_map = {
            'Élevé': COLORS['danger'],
            'Modéré': COLORS['warning'],
            'Faible': COLORS['success']
        }
        colors = [colors_map.get(label, COLORS['info']) for label in labels]

        # Create pie
        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, colors=colors, autopct='%1.0f%%',
            startangle=90, textprops={'fontsize': 11, 'fontweight': 'bold'}
        )

        # Make percentage text white
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(12)
            autotext.set_fontweight('bold')

        ax.set_title('Répartition des Risques par Sévérité',
                    fontsize=14, fontweight='bold', pad=20)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    return output_path


def create_positioning_radar(
    positioning_scores: Dict[str, float],
    output_path: str
) -> str:
    """
    Create radar chart for positioning scores.

    positioning_scores: {
        'Solidité financière': 4.0,
        'Maturité': 3.5,
        'Crédibilité marché': 3.0,
        'Exposition internationale': 2.0,
        'Gouvernance': 4.5
    }
    """
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))

    if not positioning_scores or all(v == 0 for v in positioning_scores.values()):
        # Empty chart
        ax.text(0, 0, 'Données de positionnement\nnon disponibles',
                ha='center', va='center', fontsize=12, color='gray')
        ax.set_ylim(0, 5)
    else:
        categories = list(positioning_scores.keys())
        values = list(positioning_scores.values())

        # Number of variables
        N = len(categories)

        # Compute angle for each axis
        angles = [n / float(N) * 2 * np.pi for n in range(N)]
        values += values[:1]  # Complete the circle
        angles += angles[:1]

        # Plot
        ax.plot(angles, values, 'o-', linewidth=2, color=COLORS['primary'], label='Score')
        ax.fill(angles, values, alpha=0.25, color=COLORS['primary'])

        # Fix axis to go from 0-5
        ax.set_ylim(0, 5)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=10)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_yticklabels(['1', '2', '3', '4', '5'], fontsize=9)
        ax.grid(True)

        # Add title
        ax.set_title('Profil de Positionnement Crédit',
                    fontsize=14, fontweight='bold', pad=20, y=1.08)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    return output_path


def create_sector_comparison_multi_bar(
    sector_stats: Dict,
    company_stats: Dict,
    output_path: str
) -> str:
    """
    Create multi-bar chart comparing company vs sector on multiple metrics.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Metrics to compare
    metrics_data = {
        'Capital (k DT)': {
            'Entreprise': company_stats.get('capital', 0) / 1000,
            'Médiane secteur': sector_stats.get('capital_mediane', 0) / 1000
        },
        'Effectif': {
            'Entreprise': company_stats.get('emploi', 0),
            'Médiane secteur': sector_stats.get('emploi_mediane', 0)
        },
        'Ancienneté (ans)': {
            'Entreprise': company_stats.get('age', 0),
            'Médiane secteur': sector_stats.get('age_moyen', 0)
        }
    }

    # Filter out metrics where both values are 0
    metrics_data = {
        k: v for k, v in metrics_data.items()
        if v['Entreprise'] != 0 or v['Médiane secteur'] != 0
    }

    if not metrics_data:
        ax.text(0.5, 0.5, 'Données de comparaison non disponibles',
                ha='center', va='center', fontsize=14, color='gray')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
    else:
        x = np.arange(len(metrics_data))
        width = 0.35

        company_vals = [v['Entreprise'] for v in metrics_data.values()]
        sector_vals = [v['Médiane secteur'] for v in metrics_data.values()]

        bars1 = ax.bar(x - width/2, company_vals, width, label='Entreprise',
                      color=COLORS['primary'], alpha=0.7, edgecolor='black')
        bars2 = ax.bar(x + width/2, sector_vals, width, label='Médiane secteur',
                      color=COLORS['info'], alpha=0.7, edgecolor='black')

        # Add value labels
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{height:.0f}',
                           ha='center', va='bottom', fontsize=9)

        ax.set_xticks(x)
        ax.set_xticklabels(list(metrics_data.keys()), fontsize=10)
        ax.set_ylabel('Valeur', fontsize=11, fontweight='bold')
        ax.set_title('Comparaison Entreprise vs Secteur', fontsize=14, fontweight='bold', pad=20)
        ax.legend(fontsize=10)
        ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    return output_path


def generate_all_visualizations(
    report_data: Dict,
    company: Dict,
    stats: Dict,
    positioning: Dict,
    output_dir: str
) -> Dict[str, str]:
    """
    Generate all visualizations for a report.

    Returns:
        Dict mapping visualization names to file paths
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    company_name = company.get('denomination', 'company').replace(' ', '_')

    viz_paths = {}

    # 1. Financial summary chart
    financial_data = ( report_data.get('_meta') or {} ).get('financial_data_extracted', {})
    if financial_data:
        path = os.path.join(output_dir, f'{company_name}_financial_{timestamp}.png')
        viz_paths['financial_summary'] = create_financial_summary_chart(financial_data, path)

    # 2. Risk severity pie
    risques = ( report_data.get('s4_facteurs_risque') or {} ).get('risques', [])
    if risques:
        path = os.path.join(output_dir, f'{company_name}_risks_{timestamp}.png')
        viz_paths['risk_severity'] = create_risk_severity_pie(risques, path)

    # 3. Positioning radar
    s8 = report_data.get('s8_synthese_verdict') or {}
    positioning_scores = {
        'Solidité financière': {'Forte': 5, 'Moyenne': 3, 'Faible': 1}.get(s8.get('solidite_financiere'), 3),
        'Maturité': {'Forte': 5, 'Moyenne': 3, 'Faible': 1}.get(s8.get('maturite_stabilite'), 3),
        'Crédibilité marché': {'Forte': 5, 'Moyenne': 3, 'Faible': 1}.get(s8.get('credibilite_marche'), 3),
        'International': {'Forte': 5, 'Moyenne': 3, 'Faible': 1}.get(s8.get('exposition_internationale'), 3),
        'Gouvernance': {'Excellente': 5, 'Solide': 4, 'Acceptable': 3, 'Faible': 1}.get(s8.get('gouvernance'), 3),
    }
    if any(positioning_scores.values()):
        path = os.path.join(output_dir, f'{company_name}_positioning_{timestamp}.png')
        viz_paths['positioning_radar'] = create_positioning_radar(positioning_scores, path)

    # 4. Sector comparison
    if stats:
        # SAFE calculation with proper None/empty handling
        def _clean_number(val):
            """Clean and convert string numbers to float"""
            if not val or val in (None, '', 'None', 'null'):
                return 0
            try:
                cleaned = str(val).replace(' ', '').replace(',', '').strip()
                return float(cleaned) if cleaned else 0
            except:
                return 0

        # Calculate age safely
        entree = company.get('entree_production', '')
        if entree and str(entree).strip() and str(entree) not in ('None', 'null', ''):
            try:
                age = datetime.now().year - int(str(entree).replace(' ', '').strip())
            except:
                age = 0
        else:
            age = 0

        company_stats = {
            'capital': _clean_number(company.get('capital', 0)),
            'emploi': _clean_number(company.get('emploi', 0)),
            'age': age
        }

        path = os.path.join(output_dir, f'{company_name}_sector_{timestamp}.png')
        viz_paths['sector_comparison'] = create_sector_comparison_multi_bar(stats, company_stats, path)

    return viz_paths


if __name__ == "__main__":
    # Test with sample data
    sample_financial = {
        'chiffre_affaires': 4250000,
        'resultat_net': 594371,
        'capitaux_propres': 4250400,
        'tresorerie_finale': 884721
    }

    sample_risks = [
        {'risque': 'Risk 1', 'severite': 'Élevé'},
        {'risque': 'Risk 2', 'severite': 'Modéré'},
        {'risque': 'Risk 3', 'severite': 'Modéré'},
        {'risque': 'Risk 4', 'severite': 'Faible'},
    ]

    print("Generating test visualizations...")
    create_financial_summary_chart(sample_financial, '/tmp/test_financial.png')
    create_risk_severity_pie(sample_risks, '/tmp/test_risks.png')
    print("✓ Test visualizations created in /tmp/")
