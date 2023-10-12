const Watchtower = require('watchtower-cash-js')

// Read these values from command line args
const RECIPIENT_BCHADDR = process.argv[2]
const QTY = process.argv[3]
const TOKEN_ID = process.argv[4]
const SENDER_SLP_ADDR = process.argv[5]
const SENDER_WIF = process.argv[6]

// // Read from environment variables
const BCH_FEE_FUNDING_CASH_ADDRESS = Buffer.from(process.env.BCH_FEE_FUNDING_CASH_ADDRESS, 'base64').toString()
const BCH_FEE_FUNDING_WIF = Buffer.from(process.env.BCH_FEE_FUNDING_WIF, 'base64').toString()

const watchtower = new Watchtower()

const data = {
  sender: {
    address: SENDER_SLP_ADDR,
    wif: SENDER_WIF
  },
  feeFunder: {
    address: BCH_FEE_FUNDING_CASH_ADDRESS,
    wif: BCH_FEE_FUNDING_WIF
  },
  tokenId: TOKEN_ID,
  recipients: [
    {
      address: RECIPIENT_BCHADDR,
      amount: parseFloat(QTY)
    }
  ]
}

watchtower.SLP.Type1.send(data).then(function (result) {
  if (result.success) {
    // Your logic here when send transaction is successful
    console.log(`https://explorer.bitcoin.com/bch/tx/${result.txid}`)
    console.log('success')
  } else {
    // Your logic here when send transaction fails
    console.log(result.error)
    console.log('failure')
  }
})
