import os
import base64
import re
import uuid

import streamlit as st
from datetime import datetime, date
import streamlit.components.v1 as components

from db import (
	add_submission,
	create_request,
	delete_request,
	add_reward_entry,
	get_rewards_adjustment_sum,
	clear_reward_entries,
	wipe_database,
	get_request_by_token,
	get_setting,
	init_db,
	is_token_used,
	list_requests,
	list_submissions,
	mark_token_used,
	set_one_time_use,
	set_setting,
	update_request_status,
)
from qr_utils import generate_qr, generate_batch_qr_codes, create_a4_print_layout, generate_passport_size_qr

APP_TITLE = "QR Request Manager"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")


def _is_valid_email(email: str) -> bool:
	return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _is_valid_phone(phone: str) -> bool:
	# Remove all non-digit characters for validation
	digits_only = re.sub(r'[^\d]', '', phone)
	# Check if it has 7-20 digits and contains only valid phone characters
	return bool(re.match(r"^[0-9+\-()\s]{7,20}$", phone)) and 7 <= len(digits_only) <= 20


def _build_form_url(base_url: str, token: str) -> str:
	sep = "&" if "?" in base_url else "?"
	return f"{base_url}{sep}view=form&token={token}"


def _get_param_value(params, key: str):
	val = params.get(key)
	# Streamlit may return dict with str or list[str]
	if isinstance(val, list):
		return val[0] if val else None
	return val


def _admin_section() -> None:
	st.header("Admin Dashboard")

	# Authentication
	if "authenticated" not in st.session_state:
		st.session_state["authenticated"] = False

	if not st.session_state["authenticated"]:
		with st.form("login_form"):
			pwd = st.text_input("Admin Password", type="password")
			submit = st.form_submit_button("Login")
		if submit:
			if pwd == ADMIN_PASSWORD:
				st.session_state["authenticated"] = True
				st.success("Logged in")
			else:
				st.error("Invalid password")
		st.stop()

	# Settings
	st.subheader("Settings")
	current_base = get_setting("base_url", "") or ""
	
	# Quick setup for local testing
	st.markdown("**Quick Setup for Local Testing:**")
	col1, col2 = st.columns(2)
	with col1:
		if st.button("Use Current LAN IP (192.168.1.4:8501)"):
			set_setting("base_url", "http://192.168.1.4:8501")
			st.success("Set to LAN IP - QR codes will work on your local network!")
			st.rerun()
	with col2:
		if st.button("Use Localhost (localhost:8501)"):
			set_setting("base_url", "http://localhost:8501")
			st.success("Set to localhost - QR codes will work locally!")
			st.rerun()
	
	new_base = st.text_input(
		"External Base URL (used in QR)",
		value=current_base,
		placeholder="http://192.168.1.4:8501 or https://your-domain.com",
		help="Full URL where this app is reachable from mobile devices scanning the QR.",
	)
	if st.button("Save Settings"):
		set_setting("base_url", new_base.strip())
		st.success("Settings saved")

	st.divider()

	# Dangerous zone - Database tools
	with st.expander("Danger Zone: Database Tools", expanded=False):
		st.warning("⚠️ This will permanently delete ALL data (settings, requests, submissions).")
		confirm_text = st.text_input("Type DELETE to confirm", value="", help="This cannot be undone")
		col_del1, col_del2 = st.columns(2)
		with col_del1:
			perform_backup = st.checkbox("I have backed up my data", value=False)
		with col_del2:
			delete_btn = st.button("Delete ALL data", type="primary", disabled=confirm_text != "DELETE" or not perform_backup)
		if delete_btn:
			try:
				wipe_database()
				st.success("All database records have been deleted.")
				st.info("You can start fresh by creating new requests.")
				st.balloons()
			except Exception as e:
				st.error(f"Failed to wipe database: {e}")

	# Quick Links
	st.subheader("Quick Links")
	col1, col2 = st.columns(2)
	with col1:
		st.markdown("[📊 Review All Submissions](?view=review)")
	with col2:
		st.markdown("**Review URL:** `?view=review`")

	st.divider()

	# Create Request
	st.subheader("Create New Request")
	with st.form("create_request_form"):
		title = st.text_input("Title", placeholder="e.g., Event Registration")
		description = st.text_area("Description", placeholder="Short description (optional)")
		
		# Points System
		st.markdown("**Points System**")
		points = st.number_input("Points to Award", min_value=0, value=10, help="Points users will earn for submitting this form")
		
		# One-time Use Option
		st.markdown("**Usage Settings**")
		one_time_use = st.checkbox("One-time Use", value=True, help="QR code expires after one submission")
		
		# Batch Options (merged into create form)
		st.markdown("**Batch QR Options**")
		col_b1, col_b2 = st.columns(2)
		with col_b1:
			num_qr = st.number_input("Number of QR codes", min_value=1, max_value=100, value=1, help="Generate multiple QR codes in one go")
		with col_b2:
			size_label = st.selectbox("QR Size", ["45x35mm (Passport)", "35x25mm (Small)", "55x45mm (Large)"], index=0)
		size_map = {
			"45x35mm (Passport)": (45, 35),
			"35x25mm (Small)": (35, 25),
			"55x45mm (Large)": (55, 45),
		}
		selected_size = size_map[size_label]
		
		# QR Content
		st.markdown("**QR Code Content**")
		qr_type = st.radio("QR Code Content", ["Auto URL", "Custom Text"], index=0)
		custom_qr_text = ""
		if qr_type == "Custom Text":
			custom_qr_text = st.text_area("Custom QR Content", placeholder="Enter custom text for QR code")
		
		create_btn = st.form_submit_button("Create")
	if create_btn:
		if not title.strip():
			st.error("Title is required")
		else:
			created_requests = []
			qr_images = []
			qr_contents = []
			base_url = get_setting("base_url", "") or "http://192.168.1.4:8501"
			
			from qr_utils import image_to_bytes, generate_qr
			
			if int(num_qr) == 1:
				# Single request
				token = uuid.uuid4().hex
				req = create_request(title.strip(), description.strip(), token)
				created_requests.append(req)
				set_setting(f"points_{req['id']}", str(points))
				set_one_time_use(req["id"], one_time_use)
				if qr_type == "Custom Text" and custom_qr_text.strip():
					set_setting(f"qr_custom_{req['id']}", custom_qr_text.strip())
				# Build QR content
				content = custom_qr_text.strip() if qr_type == "Custom Text" and custom_qr_text.strip() else _build_form_url(base_url, token)
				qr_contents.append(content)
				from qr_utils import generate_passport_size_qr
				qr_images.append(generate_passport_size_qr(content, selected_size))
			else:
				# Batch create multiple requests
				for i in range(int(num_qr)):
					btok = uuid.uuid4().hex
					req = create_request(f"{title.strip()} #{i+1}", description.strip(), btok)
					created_requests.append(req)
					set_setting(f"points_{req['id']}", str(points))
					set_one_time_use(req["id"], one_time_use)
					# Content per QR
					content = custom_qr_text.strip() if qr_type == "Custom Text" and custom_qr_text.strip() else _build_form_url(base_url, btok)
					qr_contents.append(content)
					from qr_utils import generate_passport_size_qr
					qr_images.append(generate_passport_size_qr(content, selected_size))
			
			st.success(f"Created {len(created_requests)} request(s)")
			# If generated multiple or one, render an A4 layout for printing
			from qr_utils import create_a4_print_layout
			a4_layout = create_a4_print_layout(qr_images, selected_size)
			layout_bytes = image_to_bytes(a4_layout, "PNG")
			st.markdown("**Preview (A4 Layout):**")
			st.image(layout_bytes, caption=f"A4 Print Layout - {len(qr_images)} QR codes", use_container_width=True)
			col_dl1, col_dl2 = st.columns(2)
			with col_dl1:
				st.download_button(
					label="📥 Download A4 Print Layout (PNG)",
					data=layout_bytes,
					file_name=f"{title.strip().replace(' ','_')}_qr_{len(qr_images)}.png",
					mime="image/png",
				)
			with col_dl2:
				try:
					from reportlab.pdfgen import canvas
					from reportlab.lib.pagesizes import A4
					from reportlab.lib.utils import ImageReader
					import io
					pdf_buf = io.BytesIO()
					c = canvas.Canvas(pdf_buf, pagesize=A4)
					img_buf = io.BytesIO(layout_bytes)
					img_reader = ImageReader(img_buf)
					c.drawImage(img_reader, 0, 0, width=A4[0], height=A4[1])
					c.save()
					st.download_button("📄 Download A4 Print (PDF)", data=pdf_buf.getvalue(), file_name=f"{title.strip().replace(' ','_')}_qr_{len(qr_images)}.pdf", mime="application/pdf")
				except Exception:
					st.info("Install 'reportlab' to enable PDF downloads: pip install reportlab")
			
			# Print button
			st.markdown("""
			<div style="text-align:center; margin: 16px 0;">
				<button onclick="window.print()" style="background:#4CAF50;color:white;border:none;padding:12px 24px;border-radius:4px;cursor:pointer;">🖨️ Print A4 Page</button>
			</div>
			""", unsafe_allow_html=True)

	st.divider()

	# Batch QR Generation
	st.subheader("Batch QR Code Generation")
	with st.form("batch_qr_form"):
		st.markdown("**Generate multiple QR codes for printing**")
		
		# QR Content
		batch_qr_type = st.radio("QR Code Content", ["Auto URL", "Custom Text"], key="batch_qr_type", index=0)
		batch_custom_text = ""
		if batch_qr_type == "Custom Text":
			batch_custom_text = st.text_area("Custom QR Content", key="batch_custom_text", placeholder="Enter custom text for QR codes")
		
		# Batch settings
		col1, col2 = st.columns(2)
		with col1:
			qr_count = st.number_input("Number of QR codes", min_value=1, max_value=100, value=10, help="How many QR codes to generate")
		with col2:
			qr_size_mm = st.selectbox("QR Size", ["45x35mm (Passport)", "35x25mm (Small)","55x45mm (Large)"], index=0)
		
		# Parse size
		size_map = {
			"45x35mm (Passport)": (45, 35),
			"35x25mm (Small)": (35, 25),
			"55x45mm (Large)": (55, 45)
		}
		selected_size = size_map[qr_size_mm]
		
		generate_batch_btn = st.form_submit_button("Generate Batch QR Codes")
	
	if generate_batch_btn:
		if batch_qr_type == "Custom Text" and not batch_custom_text.strip():
			st.error("Please enter custom text for QR codes")
		else:
			# Generate batch QR codes
			try:
				qr_images = []
				qr_contents = []
				
				if batch_qr_type == "Custom Text":
					# For custom text, all QR codes have the same content
					qr_content = batch_custom_text.strip()
					qr_images = generate_batch_qr_codes(qr_content, qr_count, selected_size)
					qr_contents = [qr_content] * qr_count
				else:
					# For Auto URL, create individual requests with unique tokens
					base_url = get_setting("base_url", "") or ""
					if not base_url:
						base_url = "http://192.168.1.12:8501"
					
					# Create individual requests for each QR code
					for i in range(qr_count):
						token = uuid.uuid4().hex
						title = f"Batch QR #{i+1}"
						description = f"Generated QR code #{i+1} from batch"
						
						# Create request
						req = create_request(title, description, token)
						
						# Set one-time use for batch QR codes
						set_one_time_use(req["id"], True)
						
						# Set default points for batch QR codes
						set_setting(f"points_{req['id']}", "5")
						
						# Generate form URL
						form_url = _build_form_url(base_url, token)
						qr_contents.append(form_url)
						
						# Generate QR code
						qr_img = generate_passport_size_qr(form_url, selected_size)
						qr_images.append(qr_img)
				
				st.success(f"✅ **Successfully generated {len(qr_images)} QR codes!**")
				st.info(f"🎯 **Each QR code:** One-time use, 5 points reward, passport size ({qr_size_mm[0]}x{qr_size_mm[1]}mm)")
				
				# Create A4 print layout
				a4_layout = create_a4_print_layout(qr_images, selected_size)
				
				# Display preview
				st.markdown("**Preview (A4 Layout):**")
				from qr_utils import image_to_bytes
				layout_bytes = image_to_bytes(a4_layout, "PNG")
				st.image(layout_bytes, caption=f"A4 Print Layout - {qr_count} QR codes", use_column_width=True)
				
				# Download options
				col1, col2 = st.columns(2)
				with col1:
					st.download_button(
						label="📥 Download A4 Print Layout (PNG)",
						data=layout_bytes,
						file_name=f"qr_batch_{qr_count}_codes.png",
						mime="image/png"
					)
				with col2:
					# Convert to PDF for better printing
					try:
						from reportlab.pdfgen import canvas
						from reportlab.lib.pagesizes import A4
						from reportlab.lib.utils import ImageReader
						import io
						
						pdf_buffer = io.BytesIO()
						pdf_canvas = canvas.Canvas(pdf_buffer, pagesize=A4)
						
						# Convert PIL image to reportlab format
						img_buffer = io.BytesIO()
						a4_layout.save(img_buffer, format='PNG')
						img_buffer.seek(0)
						img_reader = ImageReader(img_buffer)
						
						# Add image to PDF
						pdf_canvas.drawImage(img_reader, 0, 0, width=A4[0], height=A4[1])
						pdf_canvas.save()
						
						pdf_data = pdf_buffer.getvalue()
						pdf_buffer.close()
						
						st.download_button(
							label="📄 Download A4 Print Layout (PDF)",
							data=pdf_data,
							file_name=f"qr_batch_{qr_count}_codes.pdf",
							mime="application/pdf"
						)
					except ImportError:
						st.info("💡 Install reportlab for PDF download: pip install reportlab")
				
				# Print button
				st.markdown("**Print Options:**")
				st.markdown("""
				<div style="text-align: center; margin: 20px 0;">
					<button onclick="window.print()" style="
						background-color: #4CAF50;
						border: none;
						color: white;
						padding: 15px 32px;
						text-align: center;
						text-decoration: none;
						display: inline-block;
						font-size: 16px;
						margin: 4px 2px;
						cursor: pointer;
						border-radius: 4px;
					">🖨️ Print A4 Page</button>
				</div>
				""", unsafe_allow_html=True)
				
				# Store in session state for printing
				st.session_state["print_layout"] = layout_bytes
				
			except Exception as e:
				st.error(f"Error generating batch QR codes: {e}")

	st.divider()

	# Requests List
	st.subheader("All Requests")
	status_filter = st.selectbox("Filter by status", ["all", "open", "closed"], index=0)
	reqs = list_requests(None if status_filter == "all" else status_filter)

	if not reqs:
		st.info("No requests yet.")
		return

	base_url = get_setting("base_url", "") or ""

	for r in reqs:
		with st.expander(f"#{r['id']} - {r['title']} ({r['status']})", expanded=False):
			st.write(r.get("description") or "")
			token = r["token"]
			
			# Check for custom QR text and points
			custom_qr_text = get_setting(f"qr_custom_{r['id']}", "")
			points = get_setting(f"points_{r['id']}", "0")
			
			# Show points information
			if points and int(points) > 0:
				st.info(f"🎯 **Points:** {points} points awarded per submission")
			
			if custom_qr_text:
				# Generate QR with custom text
				try:
					img = generate_qr(custom_qr_text)
					from qr_utils import image_to_bytes
					img_bytes = image_to_bytes(img)
					st.image(img_bytes, caption="Custom QR Code", width='content')
				except Exception as e:
					st.error(f"QR generation error: {e}")
				st.markdown("**QR Details**")
				st.code(f"mode=Custom Text\ntoken={token}\ncontent={custom_qr_text}")
			elif base_url:
				# Generate QR with form URL
				form_url = _build_form_url(base_url, token)
				try:
					img = generate_qr(form_url)
					from qr_utils import image_to_bytes
					img_bytes = image_to_bytes(img)
					st.image(img_bytes, caption="Scan to open form", width='content')
				except Exception as e:
					st.error(f"QR generation error: {e}")
				st.markdown("**QR Details**")
				st.code(f"mode=Auto URL\ntoken={token}\nurl={form_url}")
			else:
				# Generate QR with local IP URL
				local_url = f"http://192.168.1.4:8501?view=form&token={token}"
				try:
					img = generate_qr(local_url)
					from qr_utils import image_to_bytes
					img_bytes = image_to_bytes(img)
					st.image(img_bytes, caption="Scan to open form", width='content')
				except Exception as e:
					st.error(f"QR generation error: {e}")
				
				st.markdown("**QR Details**")
				st.code(f"mode=Auto URL\ntoken={token}\nurl={local_url}")
				st.info("💡 **Tip:** Click 'Use Current LAN IP' button above to set this as the default base URL.")

			col1, col2, col3 = st.columns(3)
			with col1:
				if st.button("Close", key=f"close_{r['id']}", disabled=r["status"] == "closed"):
					update_request_status(r["id"], "closed")
					st.rerun()
			with col2:
				if st.button("Reopen", key=f"open_{r['id']}", disabled=r["status"] == "open"):
					update_request_status(r["id"], "open")
					st.rerun()
			with col3:
				if st.button("Delete", key=f"del_{r['id']}"):
					delete_request(r["id"])
					st.rerun()

			subs = list_submissions(r["id"])
			st.markdown("**Submissions**")
			if subs:
				st.table(
					[{
						"name": s["name"],
						"phone": s["phone"],
						"email": s["email"],
						"created_at": s["created_at"],
					} for s in subs]
				)
			else:
				st.caption("No submissions yet.")


def _public_form(token: str) -> None:
	req = get_request_by_token(token)
	if not req:
		st.error("Invalid or expired token.")
		st.stop()
	
	if req["status"] != "open":
		st.warning("This form is currently closed.")
		st.stop()
	
	# Check if token has been used (one-time use)
	if is_token_used(token):
		st.error("🚫 **This QR code has already been used and has expired.**")
		st.warning("⚠️ **One-time use policy:** Each QR code can only be used once for security reasons.")
		st.info("💡 **Need to submit again?** Please request a new QR code from the administrator.")
		
		# Show a disabled form for visual feedback
		st.markdown("""
		<div style="background-color: #ffebee; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center; border: 2px solid #f44336;">
			<h3 style="color: #d32f2f; margin: 0 0 10px 0;">🚫 Form Expired</h3>
			<p style="color: #666; margin: 0;">This QR code has been used and is no longer active.</p>
			<p style="color: #666; margin: 10px 0 0 0; font-size: 14px;">Please contact the administrator for a new QR code.</p>
		</div>
		""", unsafe_allow_html=True)
		
		# Show form fields as disabled
		with st.form("expired_form", clear_on_submit=False):
			st.markdown("**Form Details (Expired):**")
			st.text_input("Full Name", value="[QR Code Expired]", disabled=True)
			st.text_input("Mobile Number", value="[QR Code Expired]", disabled=True)
			st.text_input("Email Address", value="[QR Code Expired]", disabled=True)
			st.form_submit_button("Submit Form", disabled=True, help="This form has expired")
		
		st.stop()

	st.header(req["title"])

	if req.get("description"):
		st.caption(req["description"])
	
	# Points are tracked internally but not shown on the public form
	points = get_setting(f"points_{req['id']}", "0")

	with st.form("submission_form"):
		st.markdown("**Please fill in your details:**")
		
		name = st.text_input("Full Name *", placeholder="Enter your full name", help="This field is required")
		phone = st.text_input("Mobile Number *", placeholder="Enter your phone number (e.g., +1234567890)", help="Enter a valid phone number")
		email = st.text_input("Email Address (Optional)", placeholder="Enter your email address", help="Optional - enter a valid email if you have one")
		
		
		submit = st.form_submit_button("📤 Submit Form", type="primary", use_container_width=True)

	if submit:
		# Clear any previous messages
		st.empty()
		
		# Validation
		errors = []
		warnings = []
		
		# Name validation
		if not name.strip():
			errors.append("❌ **Name is required** - Please enter your full name")
		elif len(name.strip()) < 2:
			errors.append("❌ **Name too short** - Please enter at least 2 characters")
		elif len(name.strip()) > 100:
			errors.append("❌ **Name too long** - Please enter a name with less than 100 characters")
		
		# Phone validation
		if not phone.strip():
			errors.append("❌ **Phone number is required** - Please enter your mobile number")
		elif not _is_valid_phone(phone.strip()):
			errors.append("❌ **Invalid phone number** - Please enter a valid phone number (7-20 digits)")
		
		# Email validation
		if email.strip():
			if not _is_valid_email(email.strip()):
				errors.append("❌ **Invalid email format** - Please enter a valid email address or leave it empty")
			elif len(email.strip()) > 100:
				errors.append("❌ **Email too long** - Please enter an email with less than 100 characters")
		else:
			warnings.append("ℹ️ **No email provided** - You can add your email for future communications")
		
		# Display errors
		if errors:
			st.error("**Please fix the following errors:**")
			for error in errors:
				st.markdown(error)
			st.stop()
		
		# Display warnings
		if warnings:
			for warning in warnings:
				st.warning(warning)
		
		# If validation passes, submit the form
		try:
			# Add submission and mark token as used
			add_submission(req["id"], name.strip(), phone.strip(), email.strip())
			mark_token_used(token)
			
			# Success messages (no points messaging on public form)
			st.success("✅ **Form submitted successfully!**")
			st.success("🎉 **Thank you for your submission!**")
			st.balloons()
			
			# Show expiration message
			st.error("⚠️ **This QR code has now expired and cannot be used again.**")
			st.info("💡 **Need to submit again?** Please request a new QR code from the administrator.")
			
			# Disable the form
			st.markdown("""
			<div style="background-color: #ffebee; padding: 15px; border-radius: 5px; margin: 10px 0; text-align: center;">
				<strong>🚫 Form Closed</strong><br>
				This QR code has been used and is no longer active.
			</div>
			""", unsafe_allow_html=True)
			
		except ValueError as e:
			if "phone number already exists" in str(e):
				st.error("❌ **Duplicate submission detected!**")
				st.warning("⚠️ **This phone number has already been used for this form.**")
				st.info("💡 **Each person can only submit once per QR code.** Please use a different phone number or request a new QR code.")
			else:
				st.error(f"❌ **Validation error:** {str(e)}")
		except Exception as e:
			st.error(f"❌ **Submission failed:** {str(e)}")
			st.error("Please try again or contact support if the problem persists.")


def _review_page() -> None:
	st.header("📊 Review Submissions")
	
	# Get all requests with their submissions
	all_requests = list_requests()
	
	if not all_requests:
		st.info("No requests found.")
		return
	
	# Filters
	st.subheader("Filters")
	colf1, colf2 = st.columns(2)
	with colf1:
		name_filter = st.text_input("Filter by Name", placeholder="e.g., John")
	with colf2:
		phone_filter = st.text_input("Filter by Mobile", placeholder="e.g., 98765")
	
	use_date = st.checkbox("Filter by Date Range", value=False)
	start_date: date = None
	end_date: date = None
	if use_date:
		cold1, cold2 = st.columns(2)
		with cold1:
			start_date = st.date_input("Start date")
		with cold2:
			end_date = st.date_input("End date")
		if start_date and end_date and start_date > end_date:
			st.warning("Start date is after end date; date filter ignored.")
			start_date = None
			end_date = None

	# Helper to check filters
	def _matches_filters(s: dict, req_id: int) -> bool:
		if name_filter and name_filter.strip().lower() not in (s["name"] or "").lower():
			return False
		if phone_filter and phone_filter.strip() not in (s["phone"] or ""):
			return False
		if use_date and (start_date or end_date):
			created = s.get("created_at") or ""
			match_dt: datetime = None
			try:
				match_dt = datetime.fromisoformat(created)
			except Exception:
				# Best effort: take first 10 chars as date
				try:
					match_dt = datetime.strptime(created[:10], "%Y-%m-%d")
				except Exception:
					match_dt = None
			if match_dt is None:
				return False
			if start_date and match_dt.date() < start_date:
				return False
			if end_date and match_dt.date() > end_date:
				return False
		return True

	# Collect totals and show per-request sections
	total_submissions = 0
	all_filtered_rows = []  # for rewards aggregation
	for req in all_requests:
		subs = list_submissions(req["id"])
		if not subs:
			continue
		# Points for this request
		points_str = get_setting(f"points_{req['id']}", "0")
		try:
			req_points = int(points_str or 0)
		except ValueError:
			req_points = 0
		
		# Apply filters
		filtered_subs = [s for s in subs if _matches_filters(s, req["id"]) ]
		total_submissions += len(filtered_subs)
		if not filtered_subs:
			continue
		
		points_text = f" ({req_points} points each)" if req_points > 0 else ""
		with st.expander(f"📋 {req['title']} ({len(filtered_subs)} submissions){points_text}", expanded=False):
			st.write(f"**Description:** {req.get('description', 'No description')}")
			st.write(f"**Status:** {req['status']}")
			if req_points > 0:
				st.write(f"**Points Awarded:** {req_points} per submission")
			
			# Display submissions in a table
			submission_data = []
			for s in filtered_subs:
				row = {
					"Name": s["name"],
					"Phone": s["phone"],
					"Email": s["email"] or "Not provided",
					"Submitted": s["created_at"],
				}
				submission_data.append(row)
				all_filtered_rows.append((s["name"], s["phone"], req_points))
			
			if submission_data:
				st.table(submission_data)
				# Download button for this request
				import pandas as pd
				df = pd.DataFrame(submission_data)
				csv = df.to_csv(index=False)
				st.download_button(
					label=f"📥 Download {req['title']} Submissions",
					data=csv,
					file_name=f"{req['title']}_submissions.csv",
					mime="text/csv",
					key=f"dl_subs_{req['id']}"
				)

	# Totals metric after filtering
	st.metric("Total Submissions (filtered)", total_submissions)
	
	# Rewards aggregation table (by Name + Phone)
	st.subheader("Rewards Summary (by Name & Mobile)")
	if not all_filtered_rows:
		st.info("No matching submissions for the selected filters.")
		return
	
	# Aggregate
	agg: dict = {}
	for name_val, phone_val, pts in all_filtered_rows:
		key = (name_val or "", phone_val or "")
		if key not in agg:
			agg[key] = {"Name": key[0], "Phone": key[1], "Earned Points": 0, "Adjustments": 0, "Balance": 0, "Submissions": 0}
		agg[key]["Earned Points"] += max(0, int(pts or 0))
		agg[key]["Submissions"] += 1
	
	# Pull adjustments from ledger and compute balance
	for key, row in agg.items():
		adj = get_rewards_adjustment_sum(row["Name"], row["Phone"])  # negative to deduct
		row["Adjustments"] = adj
		row["Balance"] = max(0, int(row["Earned Points"]) + int(adj))
	
	# Render table
	import pandas as pd
	agg_rows = list(agg.values())
	# Sort by Total Points desc, then Name
	agg_rows.sort(key=lambda r: (-r["Total Points"], r["Name"]))
	st.table(agg_rows)
	
	# Download rewards summary
	df_rewards = pd.DataFrame(agg_rows)
	st.download_button(
		label="📥 Download Rewards Summary (CSV)",
		data=df_rewards.to_csv(index=False),
		file_name="rewards_summary.csv",
		mime="text/csv",
		key="dl_rewards_summary"
	)

	# Reward Actions section
	st.subheader("Reward Actions")
	st.caption("Apply adjustments or mark rewards as paid (zero out). Use negative points to deduct.")
	with st.form("rewards_actions_form"):
		colu1, colu2 = st.columns(2)
		with colu1:
			act_name = st.text_input("Name", placeholder="Exact name")
		with colu2:
			act_phone = st.text_input("Mobile", placeholder="Exact mobile number")
		colv1, colv2 = st.columns(2)
		with colv1:
			adj_points = st.number_input("Adjustment points (negative to deduct)", value=0, step=1)
		with colv2:
			reason = st.text_input("Reason", placeholder="e.g., redeemed, correction", value="")
		colb1, colb2, colb3 = st.columns(3)
		with colb1:
			btn_add_adj = st.form_submit_button("Add Adjustment")
		with colb2:
			btn_pay_all = st.form_submit_button("Pay (Zero Out)")
		with colb3:
			btn_delete = st.form_submit_button("Delete All Adjustments")

	if btn_add_adj:
		if not act_name.strip() or not act_phone.strip():
			st.error("Enter Name and Mobile to apply an adjustment.")
		else:
			try:
				add_reward_entry(act_name.strip(), act_phone.strip(), int(adj_points), reason.strip())
				st.success("Adjustment added.")
			except Exception as e:
				st.error(f"Failed to add adjustment: {e}")
	if btn_pay_all:
		if not act_name.strip() or not act_phone.strip():
			st.error("Enter Name and Mobile to pay.")
		else:
			# Zero out: add negative of current balance via adjustment
			try:
				current_adj = get_rewards_adjustment_sum(act_name.strip(), act_phone.strip())
				# recompute earned from current filtered agg if present
				earned = 0
				for row in agg_rows:
					if row["Name"] == act_name.strip() and row["Phone"] == act_phone.strip():
						earned = int(row.get("Earned Points", 0))
						break
				balance = max(0, earned + current_adj)
				if balance == 0:
					st.info("Balance already zero.")
				else:
					add_reward_entry(act_name.strip(), act_phone.strip(), -balance, "paid")
					st.success("Marked as paid and zeroed balance.")
			except Exception as e:
				st.error(f"Failed to pay: {e}")
	if btn_delete:
		if not act_name.strip() or not act_phone.strip():
			st.error("Enter Name and Mobile to delete adjustments.")
		else:
			try:
				clear_reward_entries(act_name.strip(), act_phone.strip())
				st.success("Deleted all adjustments for this person.")
			except Exception as e:
				st.error(f"Failed to delete adjustments: {e}")


def main() -> None:
	st.set_page_config(page_title=APP_TITLE, page_icon="📱", layout="centered")
	init_db()
	
	# Add CSS for A4 printing
	st.markdown("""
	<style>
	@media print {
		@page {
			size: A4;
			margin: 0.5in;
		}
		.stApp > div {
			visibility: hidden;
		}
		.stApp > div:has(.print-content) {
			visibility: visible;
		}
		.print-content {
			visibility: visible;
		}
		.no-print {
			display: none !important;
		}
	}
	.print-content {
		display: none;
	}
	</style>
	""", unsafe_allow_html=True)

	# Support both modern and legacy query params access
	params = getattr(st, "query_params", None)
	if params is None:
		params = st.experimental_get_query_params()

	view = _get_param_value(params, "view")
	token = _get_param_value(params, "token")

	st.title(APP_TITLE)

	if view == "form" and token:
		_public_form(token)
	elif view == "review":
		_review_page()
	else:
		_admin_section()


if __name__ == "__main__":
	main()
