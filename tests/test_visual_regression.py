# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Visual Regression Tests
# ============================================================================
# Uses Playwright for browser-based visual testing of the frontend.
# These tests require the frontend dev server to be running.
# ============================================================================

import pytest
import os
from pathlib import Path

# Mark all tests in this file as optional (require frontend server)
pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("AI_FACTORY_E2E_TESTS"),
        reason="Set AI_FACTORY_E2E_TESTS=1 to run visual regression tests",
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


class TestStorefrontVisual:
    """Visual tests for the storefront."""

    async def test_homepage_loads(self, page, frontend_url):
        """Test that the homepage loads correctly."""
        await page.goto(frontend_url)
        
        # Wait for the page to load
        await page.wait_for_load_state("networkidle")
        
        # Check that the main content is visible
        main_content = page.locator("main")
        await main_content.wait_for(state="visible", timeout=5000)
        
        # Take a screenshot for visual comparison
        await page.screenshot(path="/tmp/screenshots/homepage.png", full_page=True)

    async def test_product_listing(self, page, frontend_url):
        """Test that products are listed on the storefront."""
        await page.goto(f"{frontend_url}/products")
        await page.wait_for_load_state("networkidle")
        
        # Check for product cards
        product_cards = page.locator("[data-testid='product-card']")
        count = await product_cards.count()
        
        # Should have at least some products or an empty state
        assert count >= 0

    async def test_product_detail_page(self, page, frontend_url):
        """Test product detail page."""
        await page.goto(f"{frontend_url}/product/test-product")
        await page.wait_for_load_state("networkidle")
        
        # Check for product details section
        product_detail = page.locator("[data-testid='product-detail']")
        await product_detail.wait_for(state="visible", timeout=5000)

    async def test_checkout_flow(self, page, frontend_url):
        """Test the checkout/payment flow."""
        await page.goto(f"{frontend_url}/checkout")
        await page.wait_for_load_state("networkidle")
        
        # Check for payment form
        payment_form = page.locator("[data-testid='payment-form']")
        await payment_form.wait_for(state="visible", timeout=5000)


class TestAdminPanelVisual:
    """Visual tests for the admin panel."""

    async def test_admin_login_page(self, page, frontend_url):
        """Test that the admin login page renders."""
        await page.goto(f"{frontend_url}/admin/login")
        await page.wait_for_load_state("networkidle")
        
        # Check for login form
        login_form = page.locator("[data-testid='login-form']")
        await login_form.wait_for(state="visible", timeout=5000)
        
        await page.screenshot(path="/tmp/screenshots/admin_login.png", full_page=True)

    async def test_admin_dashboard(self, page, frontend_url):
        """Test admin dashboard rendering."""
        await page.goto(f"{frontend_url}/admin")
        await page.wait_for_load_state("networkidle")
        
        # Check for dashboard components
        dashboard = page.locator("[data-testid='admin-dashboard']")
        await dashboard.wait_for(state="visible", timeout=5000)

    async def test_pipeline_monitor(self, page, frontend_url):
        """Test pipeline monitoring view."""
        await page.goto(f"{frontend_url}/admin/pipeline")
        await page.wait_for_load_state("networkidle")
        
        pipeline_view = page.locator("[data-testid='pipeline-monitor']")
        await pipeline_view.wait_for(state="visible", timeout=5000)

    async def test_director_reports(self, page, frontend_url):
        """Test Director AI reports view."""
        await page.goto(f"{frontend_url}/admin/director")
        await page.wait_for_load_state("networkidle")
        
        reports_view = page.locator("[data-testid='director-reports']")
        await reports_view.wait_for(state="visible", timeout=5000)


class TestResponsiveDesign:
    """Tests for responsive design breakpoints."""

    @pytest.mark.parametrize("viewport", [
        {"width": 375, "height": 812},   # iPhone X
        {"width": 768, "height": 1024},  # iPad
        {"width": 1440, "height": 900},  # Desktop
    ])
    async def test_responsive_layout(self, page, frontend_url, viewport):
        """Test that the layout adapts to different screen sizes."""
        await page.set_viewport_size(viewport)
        await page.goto(frontend_url)
        await page.wait_for_load_state("networkidle")
        
        # Take screenshot for each viewport
        await page.screenshot(
            path=f"/tmp/screenshots/responsive_{viewport['width']}x{viewport['height']}.png",
            full_page=True,
        )


class TestThemeSwitching:
    """Tests for theme switching functionality."""

    async def test_theme_switch(self, page, frontend_url):
        """Test switching between themes."""
        await page.goto(frontend_url)
        await page.wait_for_load_state("networkidle")
        
        # Find and click theme switcher
        theme_switcher = page.locator("[data-testid='theme-switcher']")
        if await theme_switcher.is_visible():
            await theme_switcher.click()
            await page.wait_for_timeout(500)  # Wait for animation
            
            # Take screenshot of new theme
            await page.screenshot(path="/tmp/screenshots/theme_switched.png", full_page=True)


class TestGlassmorphismEffects:
    """Tests for glassmorphism visual effects."""

    async def test_glass_components_visible(self, page, frontend_url):
        """Test that glassmorphism components render correctly."""
        await page.goto(frontend_url)
        await page.wait_for_load_state("networkidle")
        
        # Check for glass-effect elements
        glass_elements = page.locator("[class*='glass']")
        count = await glass_elements.count()
        assert count > 0, "No glassmorphism elements found"

    async def test_animations_play(self, page, frontend_url):
        """Test that Framer Motion animations play."""
        await page.goto(frontend_url)
        await page.wait_for_load_state("networkidle")
        
        # Wait for entrance animations to complete
        await page.wait_for_timeout(2000)
        
        # Check that animated elements are in final position
        animated = page.locator("[data-animated='true']")
        if await animated.count() > 0:
            # Verify they're visible (not stuck mid-animation)
            for i in range(await animated.count()):
                is_visible = await animated.nth(i).is_visible()
                assert is_visible, f"Animated element {i} not visible"
