import sys
import os
import json
sys.path.append("Codigo/Crawler")
sys.stdout.reconfigure(encoding='utf-8')
from config import PLANES_DIR

def run_calculator_simulation(degree_code, subject_selections, discount_type="ninguno"):
    """
    Simula la lógica de cálculo exacta de TuitionCalculator.jsx sobre una titulación.
    """
    plan_path = os.path.join(PLANES_DIR, f"{degree_code}.json")
    if not os.path.exists(plan_path):
        return {"error": f"Archivo de plan no encontrado para {degree_code}"}
    
    with open(plan_path, "r", encoding="utf-8") as pf:
        degree = json.load(pf)

    base_ects_price = degree.get("precio_credito_ects") or 16.80
    admin_fees = 45.00

    elements = degree.get("plan_estudios", {}).get("elementos_curriculares", [])

    TIER_MULTIPLIERS = {1: 1.0, 2: 1.5, 3: 3.0, 4: 4.5}
    
    total_ects = 0
    total_subject_cost = 0
    tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    tier_costs = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    selected_subjects_count = 0

    for idx, elem in enumerate(elements):
        state = subject_selections.get(idx, {"selected": False, "tier": 1})
        if state.get("selected"):
            selected_subjects_count += 1
            try:
                ects = float(elem.get("creditos_ects", 6))
            except ValueError:
                ects = 6.0

            total_ects += ects
            tier = state.get("tier", 1)
            mult = TIER_MULTIPLIERS.get(tier, 1.0)
            subject_price = ects * base_ects_price * mult

            total_subject_cost += subject_price
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            tier_costs[tier] = tier_costs.get(tier, 0.0) + subject_price

    is_privada = "privad" in (degree.get("fuente_precio") or "").lower() or "cunef" in (degree.get("universidad_nombre") or "").lower()

    discount_amount = 0.0
    final_admin_fees = admin_fees if selected_subjects_count > 0 else 0.0
    discount_label = ""
    receipt_header = "💎 Honorarios Privados Estimados" if is_privada else "💶 Importe Matrícula Pública Estimada"

    if not is_privada:
        if discount_type == "fn_general":
            discount_amount = total_subject_cost * 0.5
            final_admin_fees = final_admin_fees * 0.5
            discount_label = "Exención 50% Familia Numerosa General"
        elif discount_type in ["fn_especial", "discapacidad", "victima_violencia"]:
            discount_amount = total_subject_cost
            final_admin_fees = 0.0
            discount_label = "Exención 100% Gratuidad Total"
        elif discount_type == "beca_mec":
            discount_amount = tier_costs.get(1, 0.0)
            discount_label = "Exención Beca MEC (1ª Matrícula)"
        elif discount_type == "mh_bachillerato":
            discount_amount = min(total_subject_cost, 60.0 * base_ects_price)
            discount_label = "Exención M.H. Bachillerato/CFGS (60 ECTS)"
        elif discount_type == "bonif_99":
            discount_amount = tier_costs.get(1, 0.0) * 0.99
            discount_label = "Bonificación 99% CCAA Rendimiento"
    else:
        # Rules for Private Universities: Only MEC / MH cover equivalent public pricing cap (~16.80 €/ECTS)
        public_ects_equiv = 16.80
        if discount_type == "beca_mec":
            first_tier_ects = tier_counts.get(1, 0) * 6.0
            discount_amount = first_tier_ects * public_ects_equiv
            discount_label = "Cobertura Beca MEC (Equivalente Precio Público)"
        elif discount_type == "mh_bachillerato":
            discount_amount = min(total_ects, 60.0) * public_ects_equiv
            discount_label = "Cobertura M.H. Bachillerato (Equivalente Precio Público)"
        elif discount_type in ["fn_general", "fn_especial", "discapacidad", "bonif_99"]:
            discount_label = "Exención autonómica NO aplicable en privada"

    grand_total = max(0.0, total_subject_cost - discount_amount + final_admin_fees)

    return {
        "degree_code": degree_code,
        "degree_title": degree.get("titulo"),
        "univ_name": degree.get("universidad_nombre"),
        "is_privada": is_privada,
        "receipt_header": receipt_header,
        "base_ects_price": base_ects_price,
        "selected_subjects_count": selected_subjects_count,
        "total_ects": total_ects,
        "total_subject_cost": round(total_subject_cost, 2),
        "tier_counts": tier_counts,
        "tier_costs": {k: round(v, 2) for k, v in tier_costs.items()},
        "discount_type": discount_type,
        "discount_label": discount_label,
        "discount_amount": round(discount_amount, 2),
        "admin_fees": round(final_admin_fees, 2),
        "grand_total": round(grand_total, 2)
    }

def main():
    print("\n" + "=" * 70)
    print("      EJECUTANDO PRUEBA DE FUEGO FASE 3: 'CALCULA TU MATRÍCULA'")
    print("======================================================================\n")

    # TEST CASE 1: Universidad Pública (UCA - 2500021) - 60 ECTS 1ª Matrícula en Tarifa Ordinaria
    sub_map_1 = {i: {"selected": True, "tier": 1} for i in range(10)} # 10 subjects (60 ECTS)
    res1 = run_calculator_simulation("2500021", sub_map_1, "ninguno")

    # TEST CASE 2: Universidad Pública (UCA - 2500021) - Con Repeticiones (2ª y 3ª Matrícula) y Beca MEC
    sub_map_2 = {
        0: {"selected": True, "tier": 1},
        1: {"selected": True, "tier": 1},
        2: {"selected": True, "tier": 1},
        3: {"selected": True, "tier": 2}, # 2ª matrícula (x1.5)
        4: {"selected": True, "tier": 3}  # 3ª matrícula (x3.0)
    }
    res2 = run_calculator_simulation("2500021", sub_map_2, "beca_mec")

    # TEST CASE 3: Universidad Privada (CUNEF - 2504059) - Tarifa Privada (145 €/ECTS) y Familia Numerosa General (50%)
    sub_map_3 = {i: {"selected": True, "tier": 1} for i in range(5)} # 30 ECTS
    res3 = run_calculator_simulation("2504059", sub_map_3, "fn_general")

    # TEST CASE 4: Universidad Pública - Bonificación 99% CCAA Rendimiento Académico
    res4 = run_calculator_simulation("2500021", sub_map_1, "bonif_99")

    print(" -> CASO DE PRUEBA 1: Matrícula Completa 1º Curso (UCA - Pública - Ordinaria)")
    print(json.dumps(res1, ensure_ascii=False, indent=2))
    print("\n -> CASO DE PRUEBA 2: Repetición de Asignaturas con Beca MEC (UCA - Pública)")
    print(json.dumps(res2, ensure_ascii=False, indent=2))
    print("\n -> CASO DE PRUEBA 3: Universidad Privada con Familia Numerosa General 50% (CUNEF)")
    print(json.dumps(res3, ensure_ascii=False, indent=2))
    print("\n -> CASO DE PRUEBA 4: Bonificación 99% Rendimiento CCAA (UCA - Pública)")
    print(json.dumps(res4, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
