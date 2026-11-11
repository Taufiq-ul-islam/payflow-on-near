use near_sdk::{
    near, env, AccountId, PanicOnDefault,
    collections::LookupMap,
};

#[near(serializers = [json, borsh])]
#[derive(Clone)]
pub struct Settlement {
    pub invoice_id: String,
    pub freelancer: AccountId,
    pub amount: String,
    pub token: String,
    pub settlement_reference: String,
    pub timestamp: u64,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct PayFlow {
    pub admin: AccountId,
    pub settlements: LookupMap<String, Settlement>,
}

#[near]
impl PayFlow {

    #[init]
    pub fn new(admin: AccountId) -> Self {
        Self {
            admin,
            settlements: LookupMap::new(b"s"),
        }
    }

    // The backend's authorized account records verified settlements.
    // This is not itself a proof that a cross-chain swap occurred.
    pub fn record_settlement(
        &mut self,
        invoice_id: String,
        freelancer: AccountId,
        amount: String,
        token: String,
        settlement_reference: String,
    ) {
        assert_eq!(
            env::predecessor_account_id(),
            self.admin,
            "Unauthorized caller"
        );

        assert!(
            !invoice_id.trim().is_empty(),
            "Invalid invoice ID"
        );

        assert!(
            !amount.is_empty() && amount.bytes().all(|b| b.is_ascii_digit()),
            "Amount must contain only digits"
        );

        let amount_units = amount.parse::<u128>().unwrap_or(0);

        assert!(
            amount_units > 0,
            "Amount must be greater than zero"
        );

        assert!(
            !token.trim().is_empty(),
            "Invalid token"
        );

        assert!(
            !settlement_reference.trim().is_empty(),
            "Invalid reference"
        );

        assert!(
            self.settlements.get(&invoice_id).is_none(),
            "Invoice already settled"
        );

        let settlement = Settlement {
            invoice_id: invoice_id.clone(),
            freelancer,
            amount,
            token,
            settlement_reference,
            timestamp: env::block_timestamp(),
        };

        self.settlements.insert(&invoice_id, &settlement);
    }

    pub fn get_settlement(
        &self,
        invoice_id: String,
    ) -> Option<Settlement> {
        self.settlements.get(&invoice_id)
    }

    pub fn get_admin(&self) -> AccountId {
        self.admin.clone()
    }

    pub fn update_admin(&mut self, new_admin: AccountId) {
        assert_eq!(
            env::predecessor_account_id(),
            self.admin,
            "Unauthorized caller"
        );

        assert_ne!(
            new_admin,
            self.admin,
            "New admin must be different from current admin"
        );

        self.admin = new_admin;
    }
}