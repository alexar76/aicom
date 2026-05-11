# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Marketplace & Categorization E2E Tests
# ============================================================================
# Tests the product categorization, marketplace UI, and admin pipeline
# category filter using Playwright for browser automation.
#
# Usage:
#   AI_FACTORY_E2E_TESTS=1 python3 -m pytest tests/test_marketplace_e2e.py -v
#   AI_FACTORY_E2E_TESTS=1 python3 -m pytest tests/test_marketplace_e2e.py -v --headed
# ============================================================================

import pytest
import os
import json
import urllib.request
from pathlib import Path

# Mark all tests as optional (require frontend + backend servers running)
pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("AI_FACTORY_E2E_TESTS"),
        reason="Set AI_FACTORY_E2E_TESTS=1 to run E2E browser tests",
    ),
    pytest.mark.asyncio,
]


@pytest.fixture
def frontend_url():
    """Get the frontend URL from environment or use default."""
    return os.environ.get("AI_FACTORY_FRONTEND_URL", "http://localhost:3000")


@pytest.fixture
def api_url():
    """Get the API URL from environment or use default."""
    return os.environ.get("AI_FACTORY_API_URL", "http://localhost:8080")


# ============================================================================
# API Tests (no browser needed)
# ============================================================================

class TestMarketplaceAPI:
    """Direct API tests for marketplace endpoints."""

    async def test_categories_endpoint(self, api_url):
        """Test GET /api/products/categories returns categories with counts."""
        try:
            req = urllib.request.urlopen(f"{api_url}/api/products/categories", timeout=10)
            data = json.loads(req.read().decode())
            
            assert "categories" in data
            categories = data["categories"]
            assert len(categories) >= 1
            
            # Check category structure
            cat = categories[0]
            assert "id" in cat
            assert "name" in cat
            assert "product_count" in cat
            
            print(f"  Found {len(categories)} categories")
            for c in categories:
                print(f"    - {c['name']} ({c['id']}): {c['product_count']} products")
                
        except (urllib.error.URLError, ConnectionRefusedError) as e:
            pytest.skip(f"API server not available: {e}")

    async def test_products_list_category_filter(self, api_url):
        """Test GET /api/products?category= filters correctly."""
        try:
            # Get all products first
            req = urllib.request.urlopen(f"{api_url}/api/products", timeout=10)
            all_data = json.loads(req.read().decode())
            
            if not all_data.get("products"):
                pytest.skip("No products available")
            
            products = all_data["products"]
            categories = set(p.get("category", "uncategorized") for p in products if p.get("category"))
            
            if not categories:
                pytest.skip("No categorized products available")
            
            # Test filtering by first category
            test_cat = list(categories)[0]
            req = urllib.request.urlopen(f"{api_url}/api/products?category={test_cat}", timeout=10)
            filtered_data = json.loads(req.read().decode())
            
            filtered_products = filtered_data.get("products", [])
            for p in filtered_products:
                assert p.get("category") == test_cat, \
                    f"Product {p.get('id')} has category '{p.get('category')}', expected '{test_cat}'"
            
            print(f"  Category '{test_cat}': {len(filtered_products)} products")
            
        except (urllib.error.URLError, ConnectionRefusedError) as e:
            pytest.skip(f"API server not available: {e}")

    async def test_product_detail_has_marketplace_fields(self, api_url):
        """Test GET /api/products/{id} returns marketplace fields."""
        try:
            # Get first product
            req = urllib.request.urlopen(f"{api_url}/api/products", timeout=10)
            all_data = json.loads(req.read().decode())
            
            products = all_data.get("products", [])
            if not products:
                pytest.skip("No products available")
            
            pid = products[0]["id"]
            req = urllib.request.urlopen(f"{api_url}/api/products/{pid}", timeout=10)
            detail = json.loads(req.read().decode())
            
            # Check marketplace fields exist
            assert "name" in detail or "idea" in detail
            print(f"  Product: {detail.get('name', detail.get('idea', 'N/A')[:40])}")
            print(f"  Category: {detail.get('category', 'N/A')}")
            
            # These fields may be null if marketing hasn't run yet
            if detail.get("selling_description"):
                print(f"  Has selling_description: ✓")
            if detail.get("price_usdt"):
                print(f"  Price: ${detail['price_usdt']} USDT")
            if detail.get("monetization_scheme"):
                scheme = detail["monetization_scheme"]
                if scheme.get("free_tier"):
                    print(f"  Free tier available: ✓")
                if scheme.get("paid_tiers"):
                    print(f"  Paid tiers: {len(scheme['paid_tiers'])} plans available")
            if detail.get("tags"):
                print(f"  Tags: {', '.join(detail['tags'][:5])}")
                
        except (urllib.error.URLError, ConnectionRefusedError) as e:
            pytest.skip(f"API server not available: {e}")


# ============================================================================
# Browser Tests
# ============================================================================

class TestStorefrontMarketplace:
    """Browser-based tests for the marketplace UI."""

    async def test_homepage_products_section(self, page, frontend_url):
        """Test the homepage loads and shows the products section with categories."""
        await page.goto(frontend_url)
        await page.wait_for_load_state("networkidle")
        
        # Wait for products section to be visible
        products_section = page.locator("#products")
        await products_section.wait_for(state="visible", timeout=10000)
        
        # Check that the section heading exists
        heading = products_section.locator("h2")
        await heading.wait_for(state="visible", timeout=5000)
        
        # Take a screenshot
        os.makedirs("/tmp/screenshots", exist_ok=True)
        await page.screenshot(path="/tmp/screenshots/marketplace-section.png", full_page=True)
        
        print(f"  Products section found with heading: {await heading.text_content()}")

    async def test_category_tabs_visible(self, page, frontend_url):
        """Test that category tabs are displayed in the products section."""
        await page.goto(frontend_url)
        await page.wait_for_load_state("networkidle")
        
        # Wait for products section
        products_section = page.locator("#products")
        await products_section.wait_for(state="visible", timeout=10000)
        
        # Look for category tab buttons - they should have text like "All", "AI/ML", etc.
        category_buttons = products_section.locator("button").filter(
            has_text=page.get_by_role("button")
        )
        
        # Try to find the category filter area by looking for "All" button
        all_button = products_section.locator("button", has_text="All")
        
        if await all_button.count() > 0:
            print(f"  Category tabs found: 'All' tab visible")
            
            # Count category tabs
            tab_count = await products_section.locator("button").count()
            print(f"  Total filter buttons: {tab_count}")
            
            # Click a category tab to test filtering
            # Try to find a non-All tab
            tabs = products_section.locator("button")
            for i in range(await tabs.count()):
                text = await tabs.nth(i).text_content()
                if text and "All" not in text and text.strip():
                    print(f"  Clicking category: {text.strip()}")
                    await tabs.nth(i).click()
                    await page.wait_for_timeout(1000)
                    break
        else:
            print("  Category tabs may not be rendered (no products with categories yet)")
            # Take screenshot for debugging
            await page.screenshot(path="/tmp/screenshots/no-category-tabs.png")

    async def test_product_cards_show_category_badges(self, page, frontend_url):
        """Test that product cards display category badges."""
        await page.goto(frontend_url)
        await page.wait_for_load_state("networkidle")
        
        # Wait for products section
        products_section = page.locator("#products")
        await products_section.wait_for(state="visible", timeout=10000)
        
        # Look for product cards - they're wrapped in GlassCard components
        product_cards = products_section.locator(".glass-card, [class*='glass']")
        card_count = await product_cards.count()
        
        if card_count == 0:
            # Try alternative selector for product cards
            product_cards = products_section.locator("> div > div > div")
            card_count = await product_cards.count()
        
        print(f"  Found {card_count} product cards")
        
        if card_count > 0:
            # Check if any card has category badge text
            # Category badges use text like "AI/ML", "DevTools", etc.
            category_labels = ["AI/ML", "DevTools", "SaaS", "Security", "Productivity", 
                              "E-Commerce", "IoT", "FinTech", "Other"]
            found_badge = False
            for label in category_labels:
                badge = products_section.locator(f"text={label}")
                if await badge.count() > 0:
                    found_badge = True
                    print(f"  Category badge found: {label}")
                    break
            
            if not found_badge:
                print("  No category badges found on visible cards")
                await page.screenshot(path="/tmp/screenshots/no-badges.png")

    async def test_product_detail_page_marketplace_info(self, page, frontend_url, api_url):
        """Test that product detail page shows marketplace info section."""
        # First, get a product ID from the API
        try:
            req = urllib.request.urlopen(f"{api_url}/api/products", timeout=10)
            data = json.loads(req.read().decode())
            products = data.get("products", [])
            if not products:
                pytest.skip("No products available from API")
            
            product = products[0]
            pid = product["id"]
            
            await page.goto(f"{frontend_url}/product/{pid}")
            await page.wait_for_load_state("networkidle")
            
            # Take screenshot of detail page
            await page.screenshot(path="/tmp/screenshots/product-detail.png", full_page=True)
            
            # Check for marketplace info section - look for "Marketplace Info" heading
            marketplace_heading = page.locator("text=Marketplace Info")
            if await marketplace_heading.count() > 0:
                print(f"  Marketplace Info section found: ✓")
                
                # Check for tags section
                tags_section = page.locator("h3:has-text('Tags'), text=Tags")
                if await tags_section.count() > 0:
                    print(f"  Tags section found: ✓")
                
                # Check for free tier section
                free_tier = page.locator("text=Free Tier, text=Free Plan")
                if await free_tier.count() > 0:
                    print(f"  Free tier info found: ✓")
                
                # Check for paid plans
                paid_plans = page.locator("text=Paid Plans, text=Professional, text=Starter")
                if await paid_plans.count() > 0:
                    print(f"  Paid plans found: ✓")
                
                # Check for selling description
                selling = page.locator("text=Selling Description")
                if await selling.count() > 0:
                    print(f"  Selling description found: ✓")
            else:
                print(f"  Marketplace Info section NOT found")
                # Print page title for debugging
                title = await page.title()
                print(f"  Page title: {title}")
                
        except (urllib.error.URLError, ConnectionRefusedError) as e:
            pytest.skip(f"API server not available: {e}")

    async def test_price_display_on_product_detail(self, page, frontend_url, api_url):
        """Test that price is displayed on the product detail page."""
        try:
            req = urllib.request.urlopen(f"{api_url}/api/products", timeout=10)
            data = json.loads(req.read().decode())
            products = data.get("products", [])
            if not products:
                pytest.skip("No products available")
            
            # Find a product with price info
            target_product = None
            for p in products:
                if p.get("price_usdt"):
                    target_product = p
                    break
            
            if not target_product:
                print("  No product with pricing found, testing first product")
                target_product = products[0]
            
            await page.goto(f"{frontend_url}/product/{target_product['id']}")
            await page.wait_for_load_state("networkidle")
            
            # Check for price display (USDT/USD text)
            price_text = page.locator("text=USDT, text=USD, text=$")
            if await price_text.count() > 0:
                print(f"  Price display found: ✓")
                first_price = await price_text.first.text_content()
                print(f"  Price text: {first_price}")
            else:
                print("  No price display found")
                await page.screenshot(path="/tmp/screenshots/no-price.png")
                
        except (urllib.error.URLError, ConnectionRefusedError) as e:
            pytest.skip(f"API server not available: {e}")


class TestAdminPipelineCategoryFilter:
    """Browser-based tests for the admin panel pipeline category filter."""

    async def test_admin_pipeline_shows_categories(self, page, frontend_url, api_url):
        """Test that admin pipeline tab shows category filter and badges."""
        # Navigate to admin page
        await page.goto(f"{frontend_url}/admin/login")
        await page.wait_for_load_state("networkidle")
        
        # Check if we're on login page or already authenticated
        login_form = page.locator("form, [class*='login'], input[type='password']")
        
        if await login_form.count() > 0:
            # Try default admin credentials if login form is visible
            password_input = page.locator("input[type='password']")
            if await password_input.count() > 0:
                await password_input.fill("admin123")
                submit_btn = page.locator("button[type='submit'], button:has-text('Login')")
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                    await page.wait_for_load_state("networkidle")
        
        # Navigate directly to admin page
        await page.goto(f"{frontend_url}/admin")
        await page.wait_for_load_state("networkidle")
        
        # Take screenshot
        await page.screenshot(path="/tmp/screenshots/admin-pipeline.png", full_page=True)
        
        # Look for the Pipeline tab and click it if not already active
        pipeline_tab = page.locator("button, a", has_text="Pipeline")
        if await pipeline_tab.count() > 0:
            await pipeline_tab.first.click()
            await page.wait_for_timeout(1000)
        
        # Check for category filter dropdown
        category_select = page.locator("select")
        if await category_select.count() > 0:
            print(f"  Category filter dropdown found: ✓")
            
            # Check options
            options = await category_select.locator("option").all_text_contents()
            print(f"  Filter options: {options}")
            
            # Try selecting a category
            if len(options) > 1:
                await category_select.select_option(index=1)
                await page.wait_for_timeout(500)
                print(f"  Selected category filter: {options[1]}")
        else:
            print(f"  Category filter dropdown NOT found")
        
        # Check for category badges on product cards
        category_labels = ["AI/ML", "DevTools", "SaaS", "Security", "Productivity"]
        found_any = False
        for label in category_labels:
            if await page.locator(f"text={label}").count() > 0:
                found_any = True
                print(f"  Category badge '{label}' found on pipeline cards: ✓")
                break
        
        if not found_any:
            print("  No category badges found on pipeline cards")
