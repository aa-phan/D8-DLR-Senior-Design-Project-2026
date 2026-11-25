from django.shortcuts import render, redirect
from django.http import HttpResponse
from .supabase_utils import fetch_from_supabase
from django.utils.dateparse import parse_datetime
import requests
import time
from decimal import Decimal, ROUND_DOWN

CITIES = ["Austin", "Corpus Christi", "Midland", "El Paso"]

DYNAMIC_LABEL = "using Dynamic Line Ratings"
STATIC_LABEL = "reverted to Static Line Ratings"

def get_rating_row(city):
        try:
            rows = fetch_from_supabase(
                  "latest_rating",
                  {
                        "city": f"eq.{city}",
                        "select": "city,rating_amps,static_rating_amps,is_stale,is_provisional,age_minutes",
                        "limit": 1
                  },
            )
        except requests.RequestException:
            return None
        return rows[0] if rows else None

def get_upcoming_day(city):
    try:
          rows = fetch_from_supabase(
               "day_ahead_upcoming",
               {
                    "city": f"eq.{city}",
                    "select": "city,valid_time,forecast_amps,forecast_ci_lower_amps,forecast_ci_upper_amps,label,lead_minutes",
                    "limit": 4,
                    "order": "valid_time.asc"
               },
          )
    except requests.RequestException:
        return None
    return rows

# Create your views here.
def home_page(request):
    city = request.GET.get('category')

    context = {
          "isDynamic": DYNAMIC_LABEL,
          "selected_city": "",
          "thermal_limit": "-",
          "trusted_duration": "-"
    }

    if city not in CITIES:
        return render(request, "home.html", context)

    city = city.replace(" ", "_")
    city = city.upper()
    context["selected_city"] = city
    row = get_rating_row(city)

    if row is None:
        context["isDynamic"] = STATIC_LABEL
        return render(request, "home.html", context)

    if row["is_stale"] or row["rating_amps"] is None:
        context["isDynamic"] = STATIC_LABEL
        context["thermal_limit"] = Decimal(row["static_rating_amps"]).quantize(Decimal('0.001'), ROUND_DOWN)
    else:
        context["thermal_limit"] = Decimal(row["rating_amps"]).quantize(Decimal('0.001'), ROUND_DOWN)
    context["trusted_duration"] = row["age_minutes"]
    return render(request, "home.html", context)

def history(request):
    # uses history of dynamic and static ratings to compare them
    city = request.GET.get('category')

    context = {
          "isDynamic": DYNAMIC_LABEL,
          "selected_city": "",
          "thermal_limit": "-",
          "trusted_duration": "-"
    }

    if city not in CITIES:
        return render(request, "history.html", context)

    city = city.replace(" ", "_")
    city = city.upper()
    context["selected_city"] = city
    row = get_rating_row(city)

    return render(request, "history.html", context)

def forecast(request):
    city = request.GET.get('category')
    selected_city = city

    if city not in CITIES:
        return render(request, "forecast.html", {
            "rows": [],
            "selected_city": None
        })
    
    city = city.replace(" ", "_")
    city = city.upper()
    rows = get_upcoming_day(city)

    print(type(rows), rows)

    for r in rows:
        r["valid_time"] = parse_datetime(r["valid_time"])


    return render(request, "forecast.html", {
        "rows": rows,
        "selected_city": selected_city
    })