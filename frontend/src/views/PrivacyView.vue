<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
}
</script>

<template>
  <div class="min-h-screen bg-apex-darker text-white">
    <div class="max-w-3xl mx-auto px-6 py-12">

      <!-- Back link -->
      <button
        @click="goBack"
        class="flex items-center gap-2 text-gray-400 hover:text-gold transition-colors mb-8"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        Back
      </button>

      <!-- Title -->
      <h1 class="text-3xl font-bold text-gold mb-2">Privacy Policy</h1>
      <p class="text-gray-500 mb-10">Last Updated: January 2026</p>

      <!-- 1. Introduction -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">1. Introduction</h2>
        <p class="text-gray-400 leading-relaxed">
          ApexAurum ("we", "us", "our"), a Norwegian company, is the data controller for ApexAurum Cloud.
          This Privacy Policy describes how we collect, use, store, and protect your personal data when you
          use our Service at apexaurum.cloud. This policy applies to all users of the Service, regardless
          of location, and reflects our commitment to compliance with the EU General Data Protection
          Regulation (GDPR) and the Norwegian Personal Data Act (Personopplysningsloven).
        </p>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 2. Data We Collect -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">2. Data We Collect</h2>
        <div class="text-gray-400 leading-relaxed space-y-4">
          <div>
            <h3 class="text-gray-300 font-semibold mb-2">Account Data</h3>
            <p>Email address, display name (optional), and hashed password. We never store passwords in plaintext.</p>
          </div>
          <div>
            <h3 class="text-gray-300 font-semibold mb-2">Usage Data</h3>
            <p>Message counts, feature usage metrics, and subscription status. This data is used for billing, rate limiting, and service improvement.</p>
          </div>
          <div>
            <h3 class="text-gray-300 font-semibold mb-2">Content Data</h3>
            <p>Conversations with AI agents, uploaded files, and music generation prompts. This data is stored to provide persistent conversation history and file management features.</p>
          </div>
          <div>
            <h3 class="text-gray-300 font-semibold mb-2">Technical Data</h3>
            <p>IP addresses are recorded in server logs only and are not stored long-term. Browser information may be collected in the context of bug reports or support requests.</p>
          </div>
          <div>
            <h3 class="text-gray-300 font-semibold mb-2">Payment Data</h3>
            <p>All payment processing is handled by Stripe. We store only subscription status and transaction references. We never store, process, or have access to your credit card numbers or bank account details.</p>
          </div>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 3. How We Use Your Data -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">3. How We Use Your Data</h2>
        <div class="text-gray-400 leading-relaxed">
          <p class="mb-3">We process your personal data for the following purposes:</p>
          <ul class="list-disc list-inside space-y-2 ml-2">
            <li>To provide and operate the Service, including AI chat, tool execution, and file management.</li>
            <li>To process payments and manage your subscription through Stripe.</li>
            <li>To send usage warnings (approaching rate limits) and critical service notifications.</li>
            <li>To monitor for abuse and enforce our acceptable use policies.</li>
            <li>To debug issues, resolve errors, and respond to support requests.</li>
            <li>To improve the Service through anonymized, aggregated analysis of usage patterns.</li>
          </ul>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 4. AI Data Processing -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">4. AI Data Processing</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>
            When you interact with AI agents through the Service, your messages are transmitted to Anthropic
            for response generation. Anthropic processes this data under their own data retention and privacy
            policies. We recommend reviewing Anthropic's privacy policy for details on how they handle data.
          </p>
          <p>
            Music generation prompts are transmitted to Suno for processing, subject to Suno's own terms
            and privacy policies.
          </p>
          <p>
            Users who configure BYOK (Bring Your Own Key) route their AI requests directly through their
            chosen AI provider and are subject to that provider's data handling practices.
          </p>
          <p>
            We do not use your conversations or content to train AI models. Your data is used solely to
            provide the Service to you.
          </p>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 5. Third-Party Services -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">5. Third-Party Services</h2>
        <div class="text-gray-400 leading-relaxed">
          <p class="mb-3">The Service relies on the following third-party providers:</p>
          <ul class="list-disc list-inside space-y-2 ml-2">
            <li>
              <span class="text-gray-300">Stripe</span> -- PCI-compliant payment processing.
              <a href="https://stripe.com/privacy" target="_blank" rel="noopener noreferrer" class="text-gold hover:underline">stripe.com/privacy</a>
            </li>
            <li>
              <span class="text-gray-300">Anthropic</span> -- AI model inference and response generation.
              <a href="https://www.anthropic.com/privacy" target="_blank" rel="noopener noreferrer" class="text-gold hover:underline">anthropic.com/privacy</a>
            </li>
            <li>
              <span class="text-gray-300">Suno</span> -- Music generation.
              <a href="https://suno.com/privacy" target="_blank" rel="noopener noreferrer" class="text-gold hover:underline">suno.com/privacy</a>
            </li>
            <li>
              <span class="text-gray-300">Railway</span> -- Cloud hosting infrastructure for the Service's backend, frontend, and database.
            </li>
          </ul>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 6. Data Storage & Security -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">6. Data Storage & Security</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>
            Your data is stored in PostgreSQL databases hosted on Railway's cloud infrastructure.
          </p>
          <ul class="list-disc list-inside space-y-2 ml-2">
            <li>Passwords are hashed using bcrypt and are never stored in plaintext.</li>
            <li>All communications between your browser and our servers use HTTPS encryption.</li>
            <li>Authentication is managed via JWT (JSON Web Tokens) with short expiry periods.</li>
            <li>We implement reasonable technical and organizational measures to protect your data against unauthorized access, alteration, disclosure, or destruction.</li>
          </ul>
          <p>
            While we take security seriously, no method of electronic transmission or storage is 100%
            secure. We cannot guarantee absolute security, but we are committed to maintaining industry-standard
            protections for your data.
          </p>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 7. Data Retention -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">7. Data Retention</h2>
        <div class="text-gray-400 leading-relaxed">
          <ul class="list-disc list-inside space-y-2 ml-2">
            <li><span class="text-gray-300">Active accounts:</span> Your data is retained for as long as your account remains active.</li>
            <li><span class="text-gray-300">Deleted accounts:</span> Personal data is purged within 30 days of account deletion.</li>
            <li><span class="text-gray-300">Usage logs:</span> Retained for the billing period plus 90 days for auditing and dispute resolution.</li>
            <li><span class="text-gray-300">Conversations:</span> Retained until you explicitly delete them through the Service interface.</li>
            <li><span class="text-gray-300">Server logs:</span> IP addresses and technical logs are retained for a maximum of 30 days.</li>
          </ul>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 8. Your Rights (GDPR) -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">8. Your Rights (GDPR)</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>
            As a Norwegian company, we comply with the General Data Protection Regulation (GDPR) and the
            Norwegian Personal Data Act (Personopplysningsloven). Regardless of your location, you have the
            following rights with respect to your personal data:
          </p>
          <ul class="list-disc list-inside space-y-2 ml-2">
            <li><span class="text-gray-300">Right of access:</span> You may request a copy of the personal data we hold about you.</li>
            <li><span class="text-gray-300">Right to rectification:</span> You may request correction of inaccurate or incomplete personal data.</li>
            <li><span class="text-gray-300">Right to erasure:</span> You may request deletion of your account and associated personal data.</li>
            <li><span class="text-gray-300">Right to data portability:</span> You may request an export of your conversations and data in a structured format.</li>
            <li><span class="text-gray-300">Right to object:</span> You may object to the processing of your personal data in certain circumstances.</li>
            <li><span class="text-gray-300">Right to restrict processing:</span> You may request that we limit how we process your data.</li>
            <li><span class="text-gray-300">Right to lodge a complaint:</span> You have the right to lodge a complaint with the Norwegian Data Protection Authority (Datatilsynet) at
              <a href="https://www.datatilsynet.no" target="_blank" rel="noopener noreferrer" class="text-gold hover:underline">datatilsynet.no</a>.
            </li>
          </ul>
          <p>
            To exercise any of these rights, please contact us at
            <a href="mailto:support@apexaurum.cloud" class="text-gold hover:underline">support@apexaurum.cloud</a>.
            We will respond to your request within 30 days, in accordance with GDPR requirements.
          </p>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 9. Cookies & Local Storage -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">9. Cookies & Local Storage</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>
            We use browser localStorage to store JWT authentication tokens and user preferences. This is
            essential for the Service to function and does not involve tracking.
          </p>
          <ul class="list-disc list-inside space-y-2 ml-2">
            <li>We do not use tracking cookies.</li>
            <li>We do not use third-party analytics or advertising trackers.</li>
            <li>No data is shared with advertising networks.</li>
            <li>We do not engage in cross-site tracking or behavioral profiling.</li>
          </ul>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 10. Children -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">10. Children</h2>
        <p class="text-gray-400 leading-relaxed">
          The Service is not intended for users under 18 years of age. We do not knowingly collect personal
          data from minors. If we become aware that a user under the age of 18 has registered an account,
          we will take steps to delete the account and associated data promptly.
        </p>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 11. Changes to This Policy -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">11. Changes to This Policy</h2>
        <p class="text-gray-400 leading-relaxed">
          We may update this Privacy Policy periodically to reflect changes in our practices, the Service,
          or applicable laws. Material changes will be communicated through the Service. The "Last Updated"
          date at the top of this page indicates when the most recent revision was made. Your continued use
          of the Service after any changes constitutes acceptance of the revised policy.
        </p>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 12. Contact -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">12. Contact</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>
            For privacy-related questions, data access requests, or to exercise any of your rights under
            GDPR, please contact us:
          </p>
          <p>
            Email: <a href="mailto:support@apexaurum.cloud" class="text-gold hover:underline">support@apexaurum.cloud</a>
          </p>
          <p>ApexAurum, Norway</p>
        </div>
      </section>

    </div>
  </div>
</template>
