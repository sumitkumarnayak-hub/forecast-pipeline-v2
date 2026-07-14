"""
Authentication module for Planning & Forecasting Tool
"""

from app.config import IS_PRODUCTION, USER_ROLES
from core.database.engine import Database

from core.utils.session_store import (
    clear_auth_cookie,
    persist_auth_cookie,
)
from core.shared.system_details import (
    collect_system_details,
    inject_client_system_info_cookie,
)


def init_auth_session_state() -> None:
    """Ensure auth keys exist in Streamlit session state."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None


def _material_font_css() -> str:
    """Backward-compatible alias for login page."""
    from planning_suite.ui.fonts import material_font_css
    return material_font_css()


class AuthManager:
    """Handles user authentication and authorization"""

    def __init__(self):
        self.db = Database()
        init_auth_session_state()

    def _complete_login(self, user: dict, *, remember_me: bool) -> None:
        """Finish login outside st.form so system details collection works."""
        st.session_state.authenticated = True
        st.session_state.user = user
        self.db.update_last_login(user["id"])
        from core.shared.login_sync import load_user_preferences


        load_user_preferences(user["id"], self.db)

        system_details = collect_system_details()
        print(
            f"[login] user={user.get('username')} remember_me={remember_me} "
            f"system_details_chars={len(system_details)}",
            flush=True,
        )

        if remember_me:
            persist_auth_cookie(self.db, user, system_details=system_details)
        else:
            clear_auth_cookie(self.db)

        st.session_state.pop("_login_error", None)
        st.rerun()

    def _process_pending_login(self) -> bool:
        """Authenticate credentials queued from the login form (runs outside st.form)."""
        pending = st.session_state.pop("_pending_login", None)
        if not pending:
            return False

        username = pending.get("username", "").strip()
        password = pending.get("password", "")
        remember_me = bool(pending.get("remember_me", True))

        if not username or not password:
            st.session_state["_login_error"] = "Please enter both your email and password."
            return True

        user = self.db.authenticate_user(username, password)
        if not user:
            st.session_state["_login_error"] = "Invalid username or password. Please try again."
            return True

        self._complete_login(user, remember_me=remember_me)
        return True

    def login_page(self):
        """Display login page"""
        if self._process_pending_login():
            return

        st.markdown(_material_font_css(), unsafe_allow_html=True)
        st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
            html, body, [class*="css"] {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
            }
            #MainMenu { visibility: hidden; }
            footer    { visibility: hidden; }
            [data-testid="stAppViewContainer"] > section > div:first-child {
                background: #F1F5F9;
            }
            [data-testid="stAppViewContainer"] {
                background: #F1F5F9;
            }
            .main .block-container {
                background: #F1F5F9;
                padding-top: 3rem !important;
            }
            .stButton > button {
                border-radius: 6px !important;
                font-weight: 600 !important;
                font-size: 0.9rem !important;
                background: #1A73E8 !important;
                color: #FFFFFF !important;
                border: none !important;
                padding: 0.6rem 1rem !important;
            }
            .stButton > button:hover {
                background: #1557B0 !important;
            }
            .stTextInput > div > div > input {
                border-radius: 6px !important;
                border-color: #E2E8F0 !important;
                font-size: 0.875rem !important;
                background: #FFFFFF !important;
            }
            .stForm {
                border: 1px solid #E2E8F0 !important;
                border-radius: 12px !important;
                padding: 1.75rem !important;
                background: #FFFFFF !important;
                box-shadow: 0 4px 24px rgba(15,23,42,0.07) !important;
            }
        </style>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1, 1.1, 1])

        with col2:
            st.markdown("""
            <div style="text-align: center; margin: 1.5rem 0 1.75rem 0;">
                <div style="font-size: 0.63rem; font-weight: 700; letter-spacing: 0.2em;
                            text-transform: uppercase; color: #1A73E8; margin-bottom: 0.5rem;">
                    Demand Planning
                </div>
                <div style="font-size: 1.65rem; font-weight: 700; color: #0F172A;
                            letter-spacing: -0.03em; line-height: 1.2;">
                    Planning Suite
                </div>
                <div style="font-size: 0.875rem; color: #64748B; margin-top: 0.4rem;">
                    Sign in to your account
                </div>
            </div>
            """, unsafe_allow_html=True)

            inject_client_system_info_cookie()

            login_error = st.session_state.pop("_login_error", None)
            if login_error:
                st.error(login_error)

            with st.form("login_form"):
                email = st.text_input("Email", placeholder="Enter your email address")
                password = st.text_input("Password", type="password", placeholder="Enter your password")
                remember_me = st.checkbox(
                    "Keep me signed in",
                    value=True,
                    help="Stay signed in after refreshing the browser (recommended).",
                )
                st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)
                submit = st.form_submit_button("Sign In", use_container_width=True)

                if submit:
                    st.session_state["_pending_login"] = {
                        "username": email,
                        "password": password,
                        "remember_me": remember_me,
                    }
                    st.rerun()

            if not IS_PRODUCTION:
                st.markdown("""
                <div style="margin-top: 1.25rem; padding: 1rem 1.25rem;
                            background: #FFFBEB; border: 1px solid #FDE68A;
                            border-radius: 8px; font-size: 0.8rem; color: #92400E;">
                    <div style="font-weight: 600; margin-bottom: 0.35rem;">Development mode</div>
                    Default admin: <code>sumitkumar.nayak@licious.com</code> / <code>admin123</code>
                </div>
                """, unsafe_allow_html=True)

    def logout(self):
        """Logout user and clear persisted session."""
        clear_auth_cookie(self.db)
        st.session_state.authenticated = False
        st.session_state.user = None
        st.session_state.pop("_auth_cookie_bootstrap_attempts", None)
        st.session_state.pop("_system_details_backfilled", None)
        st.rerun()

    def check_permission(self, required_permission):
        """Check if current user has required permission"""
        if not st.session_state.get("authenticated") or not st.session_state.get("user"):
            return False

        user_role = st.session_state.user.get("role", "")
        permissions = USER_ROLES.get(user_role, [])

        return required_permission in permissions

    def require_permission(self, required_permission, error_message="You don't have permission to perform this action"):
        """Decorator to require specific permission"""
        if not self.check_permission(required_permission):
            st.error(error_message)
            st.stop()

    def get_current_user(self):
        """Get current logged-in user"""
        if st.session_state.get("authenticated"):
            return st.session_state.get("user")
        return None

    def is_authenticated(self):
        """Check if user is authenticated"""
        init_auth_session_state()
        return bool(st.session_state.get("authenticated", False))

    def display_user_info(self):
        """Display current user info in sidebar"""
        if not self.is_authenticated():
            return
        user = self.get_current_user()
        if not user:
            return
        st.markdown("---")
        st.markdown(
            f"<div style='font-size:0.8rem; color:#94A3B8; padding: 0 0.25rem;'>"
            f"<div style='font-weight:600; color:#CBD5E1;'>{user['full_name']}</div>"
            f"<div style='margin-top:0.15rem;'>{user['role'].title()}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='margin-top:0.6rem;'></div>", unsafe_allow_html=True)
        if st.button("Sign Out", use_container_width=True, key="sidebar_sign_out"):
            self.logout()
