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
      <h1 class="text-3xl font-bold text-gold mb-2">Terms of Service</h1>
      <p class="text-gray-500 mb-10">Last Updated: January 2026</p>

      <!-- 1. Introduction & Acceptance -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">1. Introduction & Acceptance</h2>
        <p class="text-gray-400 leading-relaxed">
          By accessing or using ApexAurum Cloud ("the Service"), available at apexaurum.cloud, you agree to be bound
          by these Terms of Service ("Terms"). ApexAurum is a company based in Norway. If you do not agree to these
          Terms, you may not use the Service. The Service is currently in public beta, and these Terms apply to all
          users during the beta period and beyond.
        </p>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 2. Service Description -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">2. Service Description</h2>
        <p class="text-gray-400 leading-relaxed">
          ApexAurum Cloud is an AI-powered chat interface featuring multiple AI agents (Azoth, Elysian, Vajra,
          Kether), tool execution, music generation, council deliberation, persistent memory, and file management.
          The Service is powered by third-party AI models and services, and provides tiered subscription plans
          with varying levels of access to features and capabilities.
        </p>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 3. Beta Status -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">3. Beta Status</h2>
        <p class="text-gray-400 leading-relaxed">
          The Service is in public beta. Features may change, be removed, or become temporarily unavailable
          without prior notice. We do not guarantee uptime or provide service level agreements during the beta
          period. Data loss may occur during beta transitions, though we make reasonable efforts to preserve
          user data. By using the Service during beta, you acknowledge and accept these conditions.
        </p>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 4. Account & Registration -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">4. Account & Registration</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>To use the Service, you must create an account. By registering, you agree that:</p>
          <ul class="list-disc list-inside space-y-2 ml-2">
            <li>You are at least 18 years of age.</li>
            <li>You will maintain only one account per person.</li>
            <li>You will provide a valid email address during registration.</li>
            <li>You are responsible for maintaining the security of your account credentials, including your password.</li>
            <li>You accept these Terms of Service as a condition of account creation.</li>
            <li>You will promptly notify us of any unauthorized use of your account.</li>
          </ul>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 5. Acceptable Use -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">5. Acceptable Use</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>You agree not to use the Service to:</p>
          <ul class="list-disc list-inside space-y-2 ml-2">
            <li>Generate illegal, harmful, abusive, threatening, or harassing content.</li>
            <li>Attempt to circumvent rate limits, tier restrictions, or other usage controls.</li>
            <li>Use automated tools, bots, or scripts to scrape, crawl, or abuse the Service.</li>
            <li>Share your account credentials with others or allow unauthorized access to your account.</li>
            <li>Reverse engineer, decompile, or attempt to extract the source code of the Service.</li>
            <li>Use the Service for any purpose that violates applicable local, national, or international laws.</li>
            <li>Impersonate any person or entity, or misrepresent your affiliation with any person or entity.</li>
          </ul>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 6. Subscriptions & Payments -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">6. Subscriptions & Payments</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>
            Paid subscription plans are billed on a monthly basis and processed through Stripe. The following
            plans are available:
          </p>
          <ul class="list-disc list-inside space-y-2 ml-2">
            <li><span class="text-gray-300">Free Trial</span> -- 7 days of access at no charge.</li>
            <li><span class="text-gray-300">Seeker</span> -- $10 per month.</li>
            <li><span class="text-gray-300">Adept</span> -- $30 per month.</li>
            <li><span class="text-gray-300">Opus</span> -- $100 per month.</li>
            <li><span class="text-gray-300">Azothic</span> -- $300 per month.</li>
          </ul>
          <p>
            Feature credit packs (Spark, Flame, Inferno) are available as one-time purchases. Credit packs
            expire at the end of the month following the month of purchase.
          </p>
          <p>
            Cancellations take effect at the end of the current billing period. You will retain access to
            your plan's features until the billing period concludes. Refunds for subscription charges are
            handled on a case-by-case basis. Credit pack purchases are non-refundable.
          </p>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 7. Data & Content -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">7. Data & Content</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>
            You retain ownership of the content you submit to the Service. AI-generated outputs are provided
            "as is" without any warranty of accuracy, completeness, or fitness for any particular purpose.
          </p>
          <p>
            You should not rely on AI-generated outputs for medical, legal, financial, or safety-critical
            decisions. AI responses may contain errors, hallucinations, or outdated information.
          </p>
          <p>
            ApexAurum may use anonymized, aggregated usage data to monitor, analyze, and improve the Service.
            This aggregated data cannot be used to identify individual users.
          </p>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 8. Third-Party Services -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">8. Third-Party Services</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>The Service integrates with third-party providers, each governed by their own terms and privacy policies:</p>
          <ul class="list-disc list-inside space-y-2 ml-2">
            <li><span class="text-gray-300">Anthropic</span> -- AI model inference and response generation.</li>
            <li><span class="text-gray-300">Stripe</span> -- Secure payment processing for subscriptions and credit packs.</li>
            <li><span class="text-gray-300">Suno</span> -- Music generation capabilities.</li>
          </ul>
          <p>
            Users who enable BYOK (Bring Your Own Key) route their AI requests through their chosen provider
            and are subject to that provider's terms of service and usage policies.
          </p>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 9. Limitation of Liability -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">9. Limitation of Liability</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>
            The Service is provided on an "as is" and "as available" basis. ApexAurum makes no warranties,
            express or implied, regarding the Service, including but not limited to warranties of
            merchantability, fitness for a particular purpose, or non-infringement.
          </p>
          <p>
            ApexAurum shall not be liable for any indirect, incidental, special, consequential, or punitive
            damages arising from your use of the Service, including but not limited to damages related to
            AI-generated content, service interruptions, data loss, or unauthorized access to your account.
          </p>
          <p>
            To the maximum extent permitted by applicable law, ApexAurum's total aggregate liability for any
            claims arising from or related to the Service shall not exceed the total fees you have paid to
            ApexAurum in the three (3) months immediately preceding the event giving rise to the claim.
          </p>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 10. Termination -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">10. Termination</h2>
        <div class="text-gray-400 leading-relaxed space-y-3">
          <p>
            Either party may terminate the relationship at any time. You may delete your account through the
            settings page within the Service.
          </p>
          <p>
            Upon termination or account deletion, your personal data will be retained for a period of 30 days
            to allow for account recovery, after which it will be permanently deleted.
          </p>
          <p>
            We reserve the right to suspend or terminate accounts that violate these Terms, engage in abusive
            behavior, or otherwise jeopardize the integrity of the Service, with or without prior notice.
          </p>
        </div>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 11. Governing Law -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">11. Governing Law</h2>
        <p class="text-gray-400 leading-relaxed">
          These Terms shall be governed by and construed in accordance with the laws of Norway, without regard
          to its conflict of law provisions. Any disputes arising from or relating to these Terms or the Service
          shall be subject to the exclusive jurisdiction of the courts of Norway.
        </p>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 12. Changes -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">12. Changes to These Terms</h2>
        <p class="text-gray-400 leading-relaxed">
          We reserve the right to update or modify these Terms at any time. Material changes will be
          communicated to users through the Service. Your continued use of the Service after any changes
          to these Terms constitutes your acceptance of the revised Terms.
        </p>
      </section>

      <div class="border-t border-apex-border my-8"></div>

      <!-- 13. Contact -->
      <section class="mb-8">
        <h2 class="text-2xl font-bold text-gold mb-4">13. Contact</h2>
        <p class="text-gray-400 leading-relaxed">
          If you have questions about these Terms of Service, please contact us at
          <a href="mailto:support@apexaurum.cloud" class="text-gold hover:underline">support@apexaurum.cloud</a>.
        </p>
      </section>

    </div>
  </div>
</template>
