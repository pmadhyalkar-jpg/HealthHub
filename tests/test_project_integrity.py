from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_public_login_has_no_default_demo_credentials():
    login = read('frontend/login.html').lower()
    assert '@healthhub.local' not in login
    assert 'fillcreds' not in login
    assert 'demo credentials' not in login


def test_checkout_is_simulated_and_discloses_no_real_money():
    checkout = read('frontend/checkout.html')
    assert 'Simulate Successful Payment' in checkout
    assert 'Simulate Failed Payment' in checkout
    assert 'Cancel Checkout' in checkout
    assert 'No Real Money Involved' in checkout


def test_schema_contains_email_verification_and_payments():
    schema = read('database/schema.sql').lower()
    assert 'email_verified' in schema
    assert 'email_verification_token_hash' in schema
    assert 'create table if not exists payments' in schema
    assert "'succeeded'" in schema


def test_public_doctor_api_always_filters_verified_profiles():
    routes = read('backend/routes/doctor_routes.py')
    assert 'verified_only = True' in routes
    assert "d.verification_status = 'verified' AND u.status = 'active'" in routes


def test_yoga_has_local_illustrations_and_step_guidance():
    yoga = read('frontend/yoga.html')
    assert 'assets/images/yoga/' in yoga
    assert 'Steps' in yoga
    assert 'Watch tutorial on YouTube' in yoga
    for filename in ('mountain.svg', 'child.svg', 'cat-cow.svg', 'cobra.svg', 'tree.svg', 'savasana.svg', 'breathing.svg'):
        assert (ROOT / 'frontend' / 'assets' / 'images' / 'yoga' / filename).exists()


def test_symptom_search_is_connected_to_api():
    page = read('frontend/symptoms.html')
    route = read('backend/routes/content_routes.py')
    assert 'symptom-search' in page
    assert "request.args.get('q')" in route


def test_environment_secrets_are_not_bundled():
    assert not (ROOT / 'backend' / '.env').exists()
    assert (ROOT / 'backend' / '.env.example').exists()
